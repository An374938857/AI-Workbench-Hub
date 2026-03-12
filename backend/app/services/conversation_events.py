from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Optional

from redis.asyncio import Redis

from app.config import get_settings
from app.models.conversation import Conversation
from app.services.conversation_live_state import (
    build_live_state_detail_version,
    serialize_live_execution,
)
from app.services.conversation_sidebar_signal import serialize_sidebar_signal

logger = logging.getLogger(__name__)


class ConversationEventVersionGenerator:
    """Generate monotonic per-conversation event versions."""

    def __init__(self) -> None:
        self._last_versions: dict[int, int] = {}

    def next_version(self, conversation_id: int) -> int:
        now_ms = int(time.time() * 1000)
        prev = self._last_versions.get(conversation_id, 0)
        version = now_ms if now_ms > prev else prev + 1
        self._last_versions[conversation_id] = version
        return version


def get_conversation_event_channel(user_id: int) -> str:
    return f"conversation_events:user:{user_id}"


def build_conversation_sync_event(
    *,
    conv: Conversation,
    event_type: str,
    event_version: int,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "conversation_id": int(conv.id),
        "event_version": int(event_version),
        "event_ts": datetime.now().isoformat(),
        "patch": {
            "title": conv.title or "新对话",
            "live_execution": serialize_live_execution(conv),
            "sidebar_signal": serialize_sidebar_signal(conv),
            "sandbox_unread_change_count": int(conv.sandbox_unread_change_count or 0),
            "detail_version": build_live_state_detail_version(conv),
        },
    }


def build_simple_conversation_event(
    *,
    conversation_id: int,
    event_type: str,
    event_version: int,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "conversation_id": int(conversation_id),
        "event_version": int(event_version),
        "event_ts": datetime.now().isoformat(),
        "patch": {},
    }


class ConversationEventBus:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis: Optional[Redis] = None
        self._version_generator = ConversationEventVersionGenerator()

    @property
    def enabled(self) -> bool:
        return bool(self._settings.REDIS_URL)

    async def startup(self) -> None:
        if not self.enabled or self._redis is not None:
            return
        try:
            self._redis = Redis.from_url(self._settings.REDIS_URL, decode_responses=True)
            await self._redis.ping()
            logger.info("conversation event bus connected to redis")
        except Exception:
            logger.exception("failed to connect conversation event bus redis")
            if self._redis is not None:
                await self._redis.aclose()
            self._redis = None

    async def shutdown(self) -> None:
        if self._redis is None:
            return
        await self._redis.aclose()
        self._redis = None

    async def ensure_ready(self) -> bool:
        if self._redis is not None:
            return True
        await self.startup()
        return self._redis is not None

    async def publish(self, *, user_id: int, payload: dict[str, Any]) -> bool:
        if not await self.ensure_ready():
            return False
        assert self._redis is not None
        channel = get_conversation_event_channel(user_id)
        await self._redis.publish(channel, json.dumps(payload, ensure_ascii=False))
        return True

    async def publish_conversation_snapshot(
        self,
        *,
        conv: Conversation,
        event_type: str,
    ) -> bool:
        version = self._version_generator.next_version(int(conv.id))
        payload = build_conversation_sync_event(
            conv=conv,
            event_type=event_type,
            event_version=version,
        )
        return await self.publish(user_id=int(conv.user_id), payload=payload)

    async def publish_simple_event(
        self,
        *,
        user_id: int,
        conversation_id: int,
        event_type: str,
    ) -> bool:
        version = self._version_generator.next_version(int(conversation_id))
        payload = build_simple_conversation_event(
            conversation_id=conversation_id,
            event_type=event_type,
            event_version=version,
        )
        return await self.publish(user_id=int(user_id), payload=payload)

    def publish_conversation_snapshot_nowait(
        self,
        *,
        conv: Conversation,
        event_type: str,
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            self.publish_conversation_snapshot(
                conv=conv,
                event_type=event_type,
            )
        )

    def publish_simple_event_nowait(
        self,
        *,
        user_id: int,
        conversation_id: int,
        event_type: str,
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            self.publish_simple_event(
                user_id=user_id,
                conversation_id=conversation_id,
                event_type=event_type,
            )
        )

    async def subscribe_user(self, user_id: int):
        if not await self.ensure_ready():
            return None
        assert self._redis is not None
        channel = get_conversation_event_channel(user_id)
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        return pubsub


_event_bus: Optional[ConversationEventBus] = None


def get_conversation_event_bus() -> ConversationEventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = ConversationEventBus()
    return _event_bus
