import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable


logger = logging.getLogger(__name__)


PublishCallback = Callable[[str, dict], Awaitable[None]]
RunnerFactory = Callable[[PublishCallback], Awaitable[None]]


@dataclass
class ConversationRuntimeEntry:
    conversation_id: int
    task: asyncio.Task
    subscribers: set[asyncio.Queue] = field(default_factory=set)


class ConversationRuntimeRegistry:
    def __init__(self) -> None:
        self._entries: dict[int, ConversationRuntimeEntry] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        conversation_id: int,
        runner_factory: RunnerFactory,
    ) -> asyncio.Queue:
        async with self._lock:
            entry = self._entries.get(conversation_id)
            if entry and not entry.task.done():
                raise RuntimeError("该对话正在生成中，请稍候")

            subscriber: asyncio.Queue = asyncio.Queue()

            async def publish(event: str, data: dict) -> None:
                await self._publish(conversation_id, event, data)

            task = asyncio.create_task(
                self._run_entry(conversation_id, runner_factory, publish)
            )
            self._entries[conversation_id] = ConversationRuntimeEntry(
                conversation_id=conversation_id,
                task=task,
                subscribers={subscriber},
            )
            return subscriber

    async def subscribe(self, conversation_id: int) -> asyncio.Queue | None:
        async with self._lock:
            entry = self._entries.get(conversation_id)
            if not entry or entry.task.done():
                return None
            subscriber: asyncio.Queue = asyncio.Queue()
            entry.subscribers.add(subscriber)
            return subscriber

    async def unsubscribe(self, conversation_id: int, subscriber: asyncio.Queue) -> None:
        async with self._lock:
            entry = self._entries.get(conversation_id)
            if not entry:
                return
            entry.subscribers.discard(subscriber)

    async def cancel(self, conversation_id: int) -> bool:
        async with self._lock:
            entry = self._entries.get(conversation_id)
            if not entry or entry.task.done():
                return False
            entry.task.cancel()
            return True

    async def is_running(self, conversation_id: int) -> bool:
        async with self._lock:
            entry = self._entries.get(conversation_id)
            return bool(entry and not entry.task.done())

    async def _publish(self, conversation_id: int, event: str, data: dict) -> None:
        async with self._lock:
            entry = self._entries.get(conversation_id)
            if not entry:
                return
            subscribers = list(entry.subscribers)

        for subscriber in subscribers:
            try:
                await subscriber.put({"event": event, "data": data})
            except Exception:
                logger.exception("发布会话运行时事件失败: conversation_id=%s", conversation_id)

    async def _run_entry(
        self,
        conversation_id: int,
        runner_factory: RunnerFactory,
        publish: PublishCallback,
    ) -> None:
        try:
            await runner_factory(publish)
        except asyncio.CancelledError:
            logger.info("会话生成任务被取消: conversation_id=%s", conversation_id)
            raise
        except Exception as exc:
            logger.exception("会话生成任务异常: conversation_id=%s", conversation_id)
            await publish(
                "error",
                {
                    "type": "error",
                    "message": str(exc) or "生成任务异常",
                },
            )
        finally:
            async with self._lock:
                entry = self._entries.get(conversation_id)
                subscribers = list(entry.subscribers) if entry else []
                self._entries.pop(conversation_id, None)

            for subscriber in subscribers:
                try:
                    await subscriber.put({"event": "__close__", "data": {}})
                except Exception:
                    logger.exception(
                        "关闭会话运行时订阅失败: conversation_id=%s", conversation_id
                    )


_runtime_registry = ConversationRuntimeRegistry()


def get_conversation_runtime_registry() -> ConversationRuntimeRegistry:
    return _runtime_registry
