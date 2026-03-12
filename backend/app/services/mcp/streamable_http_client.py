import logging
from contextlib import AsyncExitStack
from typing import Optional

import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession
from mcp.types import TextContent, EmbeddedResource

from app.services.mcp.base_client import BaseMCPClient, MCPToolInfo

logger = logging.getLogger(__name__)


class StreamableHttpClient(BaseMCPClient):
    """通过 Streamable HTTP 协议与远程 MCP 服务通信"""

    def __init__(self, url: str, headers: dict | None = None, timeout: float = 30):
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        if self._session is not None:
            return

        self._exit_stack = AsyncExitStack()
        try:
            # 创建 httpx 客户端，传入 headers
            self._http_client = httpx.AsyncClient(
                headers=self._headers,
                timeout=httpx.Timeout(self._timeout, read=300.0)
            )
            await self._exit_stack.enter_async_context(self._http_client)

            # 创建 streamable-http transport
            transport = await self._exit_stack.enter_async_context(
                streamable_http_client(url=self._url, http_client=self._http_client)
            )
            read_stream, write_stream, get_session_id = transport

            # 创建 MCP session
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()
            logger.info(f"Streamable HTTP MCP 连接成功: {self._url}")
        except Exception:
            await self._cleanup()
            raise

    async def disconnect(self) -> None:
        await self._cleanup()
        logger.info(f"Streamable HTTP MCP 连接已断开: {self._url}")

    async def _cleanup(self) -> None:
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.warning(f"Streamable HTTP MCP 清理异常: {e}")
            finally:
                self._exit_stack = None
                self._session = None
                self._http_client = None

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