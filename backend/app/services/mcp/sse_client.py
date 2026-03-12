import logging
from contextlib import AsyncExitStack
from typing import Optional

from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from mcp.types import TextContent, EmbeddedResource

from app.services.mcp.base_client import BaseMCPClient, MCPToolInfo

logger = logging.getLogger(__name__)


class SSEMCPClient(BaseMCPClient):
    """通过 SSE/HTTP 与远程 MCP 服务通信"""

    def __init__(self, url: str, headers: dict | None = None, timeout: float = 5):
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None

    async def connect(self) -> None:
        if self._session is not None:
            return

        self._exit_stack = AsyncExitStack()
        try:
            transport = await self._exit_stack.enter_async_context(
                sse_client(
                    url=self._url,
                    headers=self._headers if self._headers else None,
                    timeout=self._timeout,
                )
            )
            read_stream, write_stream = transport
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()
            logger.info(f"SSE MCP 连接成功: {self._url}")
        except Exception:
            await self._cleanup()
            raise

    async def disconnect(self) -> None:
        await self._cleanup()
        logger.info(f"SSE MCP 连接已断开: {self._url}")

    async def _cleanup(self) -> None:
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.warning(f"SSE MCP 清理异常: {e}")
            finally:
                self._exit_stack = None
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
        return self._session is not None

    def _ensure_connected(self) -> None:
        if not self.is_connected():
            raise ConnectionError("MCP 客户端未连接，请先调用 connect()")

    @staticmethod
    def _extract_text(content: list) -> str:
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
