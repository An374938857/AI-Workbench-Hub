import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.services.mcp.client_manager import MCPClientManager
from app.services.mcp.circuit_breaker import CircuitBreakerRegistry, get_circuit_breaker_registry

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_CHARS = 16384


@dataclass
class ToolExecutionResult:
    """工具执行结果"""
    success: bool
    content: str
    error: Optional[str] = None
    response_time_ms: int = 0


class ToolExecutor:
    """
    工具执行器：调用 MCP 工具并返回结果。
    包含超时控制、重试、结果截断和熔断保护。
    """

    def __init__(self, client_manager: MCPClientManager, breaker_registry: Optional[CircuitBreakerRegistry] = None):
        self._client_manager = client_manager
        self._breaker_registry = breaker_registry or get_circuit_breaker_registry()

    async def execute(
        self,
        mcp_id: int,
        config_json: dict,
        transport_type: str,
        tool_name: str,
        arguments: dict,
        timeout_seconds: int = 30,
        max_retries: int = 0,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_recovery: int = 300,
    ) -> ToolExecutionResult:
        breaker = self._breaker_registry.get_or_create(mcp_id, circuit_breaker_threshold, circuit_breaker_recovery)

        if not await breaker.can_execute():
            remaining = ""
            if breaker._open_until:
                secs = max(0, int((breaker._open_until - datetime.now()).total_seconds()))
                remaining = f"，预计 {secs} 秒后恢复"
            return ToolExecutionResult(
                success=False,
                content="",
                error=f"MCP 服务暂时不可用（熔断中{remaining}）",
                response_time_ms=0,
            )

        last_error: Optional[str] = None
        elapsed_ms = 0

        for attempt in range(1 + max_retries):
            start_time = time.monotonic()
            try:
                client = await self._client_manager.get_client(mcp_id, config_json, transport_type)
                raw_result = await asyncio.wait_for(
                    client.call_tool(tool_name, arguments),
                    timeout=timeout_seconds,
                )
                elapsed_ms = int((time.monotonic() - start_time) * 1000)

                await breaker.record_success()
                content = self._truncate(raw_result)
                return ToolExecutionResult(
                    success=True,
                    content=content,
                    response_time_ms=elapsed_ms,
                )

            except asyncio.TimeoutError:
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                last_error = f"工具调用超时（{timeout_seconds}s）"
                logger.warning(f"MCP 工具调用超时: mcp_id={mcp_id}, tool={tool_name}, attempt={attempt + 1}")

            except ConnectionError as e:
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                last_error = f"MCP 连接错误: {e}"
                logger.warning(f"MCP 连接错误: mcp_id={mcp_id}, tool={tool_name}, error={e}")
                await self._client_manager.invalidate(mcp_id)

            except Exception as e:
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                last_error = str(e) or f"{type(e).__name__}: (无详细信息)"
                logger.warning(f"MCP 工具调用失败: mcp_id={mcp_id}, tool={tool_name}, error={last_error}")
                await self._client_manager.invalidate(mcp_id)

            if attempt < max_retries:
                await asyncio.sleep(1)

        await breaker.record_failure()
        return ToolExecutionResult(
            success=False,
            content="",
            error=last_error,
            response_time_ms=elapsed_ms,
        )

    @staticmethod
    def _truncate(text: str) -> str:
        if len(text) <= MAX_TOOL_RESULT_CHARS:
            return text
        return text[:MAX_TOOL_RESULT_CHARS] + "\n\n[结果已截断，仅展示前部分内容]"
