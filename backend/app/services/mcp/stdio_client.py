import asyncio
import logging
import sys
from typing import Optional

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from mcp.types import TextContent, EmbeddedResource

from app.services.mcp.base_client import BaseMCPClient, MCPToolInfo

logger = logging.getLogger(__name__)


class StdioMCPClient(BaseMCPClient):
    """通过 stdio（子进程）与 MCP 服务通信"""

    def __init__(self, command: str, args: list[str] | None = None, env: dict | None = None):
        self._server_params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )
        self._session: Optional[ClientSession] = None
        self._runner_task: Optional[asyncio.Task] = None
        self._ready_event: Optional[asyncio.Event] = None
        self._closed_event: Optional[asyncio.Event] = None
        self._disconnect_requested: Optional[asyncio.Event] = None
        self._connect_error: Optional[BaseException] = None

    async def connect(self) -> None:
        if self.is_connected():
            return

        try:
            if self._runner_task is None or self._runner_task.done():
                self._ready_event = asyncio.Event()
                self._closed_event = asyncio.Event()
                self._disconnect_requested = asyncio.Event()
                self._connect_error = None
                self._runner_task = asyncio.create_task(self._run_session())

            await self._ready_event.wait()
        except BaseException:
            await asyncio.shield(self._shutdown_runner())
            raise
        if self._connect_error is not None:
            error = self._connect_error
            await self._shutdown_runner()
            raise ConnectionError(f"stdio MCP 连接失败: {error}") from error
        logger.info(f"stdio MCP 连接成功: {self._server_params.command} {self._server_params.args}")

    async def disconnect(self) -> None:
        await self._shutdown_runner()
        logger.info(f"stdio MCP 连接已断开: {self._server_params.command}")

    async def _run_session(self) -> None:
        try:
            async with stdio_client(self._server_params, errlog=sys.stderr) as transport:
                read_stream, write_stream = transport
                async with ClientSession(read_stream, write_stream) as session:
                    self._session = session
                    await self._session.initialize()
                    self._ready_event.set()
                    await self._disconnect_requested.wait()
        except Exception as e:
            self._connect_error = e
            if self._ready_event and not self._ready_event.is_set():
                self._ready_event.set()
            else:
                logger.warning(f"stdio MCP 会话异常关闭: {e}")
        finally:
            self._session = None
            if self._ready_event and not self._ready_event.is_set():
                self._ready_event.set()
            if self._closed_event and not self._closed_event.is_set():
                self._closed_event.set()

    async def _shutdown_runner(self) -> None:
        task = self._runner_task
        if task is None:
            self._reset_runner_state()
            return

        if self._disconnect_requested and not self._disconnect_requested.is_set():
            self._disconnect_requested.set()

        try:
            if self._closed_event is not None:
                await self._closed_event.wait()
            await task
        finally:
            self._reset_runner_state()

    def _reset_runner_state(self) -> None:
        self._runner_task = None
        self._ready_event = None
        self._closed_event = None
        self._disconnect_requested = None
        self._connect_error = None
        self._session = None

    async def list_tools(self) -> list[MCPToolInfo]:
        self._ensure_connected()
        result = await self._session.list_tools()
        return [
            MCPToolInfo(
                name=t.name,
                description=t.description,
                input_schema=t.inputSchema if t.inputSchema else None,
            )
            for t in result.tools
        ]

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        self._ensure_connected()
        result = await self._session.call_tool(tool_name, arguments)
        if result.isError:
            error_text = self._extract_text(result.content)
            raise Exception(f"MCP 工具调用错误: {error_text}")
        return self._extract_text(result.content)

    def is_connected(self) -> bool:
        return self._session is not None and self._runner_task is not None and not self._runner_task.done()

    def _ensure_connected(self) -> None:
        if not self.is_connected():
            raise ConnectionError("MCP 客户端未连接，请先调用 connect()")

    @staticmethod
    def _extract_text(content: list) -> str:
        """从 MCP 响应内容中提取纯文本"""
        parts = []
        for item in content:
            if isinstance(item, TextContent):
                parts.append(item.text)
            elif isinstance(item, EmbeddedResource):
                parts.append(str(item))
            elif hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "\n".join(parts)
