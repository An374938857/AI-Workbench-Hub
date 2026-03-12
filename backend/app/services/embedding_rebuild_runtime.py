from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.database import SessionLocal
from app.models.reference import EmbeddingRebuildTask
from app.services.embedding_governance import (
    ACTIVE_TASK_STATUSES,
    process_rebuild_task_cycle,
)


logger = logging.getLogger(__name__)


@dataclass
class EmbeddingTaskEntry:
    task_id: int
    runner: asyncio.Task


class EmbeddingRebuildRuntime:
    def __init__(self) -> None:
        self._tasks: dict[int, EmbeddingTaskEntry] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, event: str, data: dict) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                await subscriber.put({"event": event, "data": data})
            except Exception:
                logger.exception("发布 embedding rebuild SSE 失败")

    async def start_task(self, task_id: int) -> bool:
        async with self._lock:
            entry = self._tasks.get(task_id)
            if entry and not entry.runner.done():
                return False
            runner = asyncio.create_task(self._run_task(task_id))
            self._tasks[task_id] = EmbeddingTaskEntry(task_id=task_id, runner=runner)
            return True

    async def startup_resume(self) -> None:
        with SessionLocal() as db:
            rows = (
                db.query(EmbeddingRebuildTask)
                .filter(EmbeddingRebuildTask.status.in_(tuple(ACTIVE_TASK_STATUSES)))
                .all()
            )
            task_ids = [row.id for row in rows]
        for task_id in task_ids:
            await self.start_task(task_id)

    async def _run_task(self, task_id: int) -> None:
        try:
            while True:
                payload = await process_rebuild_task_cycle(task_id)
                await self.publish("task_update", payload)
                if payload.get("status") not in ACTIVE_TASK_STATUSES:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("embedding rebuild task runtime failed: task_id=%s", task_id)
            await self.publish(
                "task_error",
                {"task_id": task_id, "message": str(exc) or "embedding rebuild task failed"},
            )
        finally:
            async with self._lock:
                self._tasks.pop(task_id, None)


_runtime = EmbeddingRebuildRuntime()


def get_embedding_rebuild_runtime() -> EmbeddingRebuildRuntime:
    return _runtime
