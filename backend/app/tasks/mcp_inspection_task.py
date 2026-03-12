"""
MCP 自动巡检任务
按配置频次批量测试已启用的 MCP 连通性。
"""
import asyncio
import logging
from typing import Optional

from app.database import SessionLocal
from app.models.mcp import Mcp
from app.models.system_config import SystemConfig
from app.services import mcp_service

logger = logging.getLogger(__name__)

MCP_INSPECTION_CONFIG_KEY = "mcp_inspection_interval_minutes"
DEFAULT_MCP_INSPECTION_INTERVAL_MINUTES = 30


class MCPInspectionTask:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()
        self._running_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("MCP 自动巡检任务已启动")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("MCP 自动巡检任务已停止")

    async def _run_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("MCP 自动巡检执行异常")

            interval_minutes = self._load_interval_minutes()
            timeout_seconds = max(interval_minutes * 60, 60)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=timeout_seconds)
            except TimeoutError:
                continue

    async def run_once(self) -> None:
        if self._running_lock.locked():
            logger.warning("MCP 自动巡检仍在执行，跳过本轮")
            return

        async with self._running_lock:
            db = SessionLocal()
            try:
                mcps = db.query(Mcp).filter(Mcp.is_enabled == True).all()
                if not mcps:
                    logger.info("MCP 自动巡检跳过：没有已启用 MCP")
                    return

                result = await mcp_service.run_batch_connectivity_test(db, mcps)
                logger.info(
                    "MCP 自动巡检完成：总计 %s，成功 %s，失败 %s",
                    result["total"],
                    result["success_count"],
                    result["fail_count"],
                )
            finally:
                db.close()

    def _load_interval_minutes(self) -> int:
        db = SessionLocal()
        try:
            config = db.query(SystemConfig).filter(SystemConfig.key == MCP_INSPECTION_CONFIG_KEY).first()
            if not config:
                return DEFAULT_MCP_INSPECTION_INTERVAL_MINUTES
            value = config.get_value()
            if not isinstance(value, int) or value <= 0:
                return DEFAULT_MCP_INSPECTION_INTERVAL_MINUTES
            return value
        finally:
            db.close()


_inspection_task: Optional[MCPInspectionTask] = None


def get_mcp_inspection_task() -> MCPInspectionTask:
    global _inspection_task
    if _inspection_task is None:
        _inspection_task = MCPInspectionTask()
    return _inspection_task
