import asyncio
import logging
from typing import Optional

from app.services.mcp.base_client import BaseMCPClient
from app.services.mcp.stdio_client import StdioMCPClient
from app.services.mcp.sse_client import SSEMCPClient
from app.services.mcp.streamable_http_client import StreamableHttpClient

logger = logging.getLogger(__name__)


# MCP 传输类型映射（兼容各种命名风格）
_TRANSPORT_TYPE_ALIASES = {
    "streamablehttp": "streamable-http",
    "streamable_http": "streamable-http",
    "streamable-http": "streamable-http",
    "sse": "sse",
    "stdio": "stdio",
}

# URL 字段别名
_URL_FIELD_ALIASES = ["url", "baseUrl", "base_url", "endpoint", "serverUrl"]


class MCPClientManager:
    """管理所有 MCP 客户端的连接池"""

    def __init__(self):
        self._clients: dict[int, BaseMCPClient] = {}
        self._lock = asyncio.Lock()

    async def get_client(self, mcp_id: int, config_json: dict, transport_type: str) -> BaseMCPClient:
        """获取或创建 MCP 客户端实例"""
        async with self._lock:
            if mcp_id in self._clients and self._clients[mcp_id].is_connected():
                return self._clients[mcp_id]

            client = self._create_client(config_json, transport_type)
            await client.connect()
            self._clients[mcp_id] = client
            return client

    async def invalidate(self, mcp_id: int) -> None:
        """配置变更时失效并断开缓存的客户端"""
        async with self._lock:
            if mcp_id in self._clients:
                try:
                    await self._clients[mcp_id].disconnect()
                except Exception as e:
                    logger.warning(f"MCP 客户端断开失败 (id={mcp_id}): {e}")
                del self._clients[mcp_id]

    async def shutdown(self) -> None:
        """应用关闭时断开所有连接"""
        async with self._lock:
            for mcp_id, client in self._clients.items():
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.warning(f"MCP 客户端断开失败 (id={mcp_id}): {e}")
            self._clients.clear()
            logger.info("所有 MCP 客户端连接已关闭")

    @classmethod
    def _create_client(cls, config_json: dict, transport_type: str) -> BaseMCPClient:
        """根据配置创建对应的客户端实例（未连接状态），自动处理 mcpServers 包装"""
        inner = cls.normalize_config(config_json)
        if transport_type == "stdio":
            return StdioMCPClient(
                command=inner["command"],
                args=inner.get("args", []),
                env=inner.get("env"),
            )
        elif transport_type == "sse":
            return SSEMCPClient(
                url=inner["url"],
                headers=inner.get("headers"),
                timeout=inner.get("timeout", 5),
            )
        elif transport_type == "streamable-http":
            return StreamableHttpClient(
                url=inner["url"],
                headers=inner.get("headers"),
                timeout=inner.get("timeout", 30),
            )
        else:
            raise ValueError(f"不支持的 MCP 传输方式: {transport_type}")

    @staticmethod
    def _extract_url_field(config: dict) -> Optional[str]:
        """从配置中提取 URL 字段，支持多种字段名"""
        for field in _URL_FIELD_ALIASES:
            if field in config and config[field]:
                return config[field]
        return None

    @staticmethod
    def _normalize_transport_type(type_str: str) -> str:
        """标准化传输类型名称"""
        normalized = type_str.lower().replace("-", "").replace("_", "")
        return _TRANSPORT_TYPE_ALIASES.get(normalized, type_str.lower())

    @staticmethod
    def normalize_config(config_json: dict) -> dict:
        """
        兼容多种 MCP JSON 配置格式：

        支持的格式：
        1. 直接格式：{"command": "npx", "args": [...]}
        2. 直接格式：{"url": "http://...", "type": "sse"}
        3. 包装格式（带服务名）：{"mcpServers": {"server-name": {...}}}
        4. 包装格式（不带服务名）：{"mcpServers": {"url": "...", "type": "..."}}

        字段别名支持：
        - URL字段: url, baseUrl, base_url, endpoint, serverUrl
        - 类型字段: streamable-http, streamableHttp, streamable_http, sse, stdio

        返回标准化后的内部配置。
        """
        inner = config_json

        # 处理 mcpServers 包装
        if "mcpServers" in config_json:
            servers = config_json["mcpServers"]
            if not servers or not isinstance(servers, dict):
                raise ValueError("mcpServers 配置为空或格式不正确")

            # 检查是否直接包含配置字段（无服务名嵌套）
            has_config = any(
                field in servers
                for field in ["url", "baseUrl", "base_url", "endpoint", "serverUrl", "command"]
            )
            if has_config:
                inner = servers
            else:
                # 有服务名嵌套，取第一个服务
                first_key = next(iter(servers))
                inner = servers[first_key]
                logger.debug(f"MCP 配置: 使用服务 '{first_key}'")

        # 标准化 URL 字段
        url = MCPClientManager._extract_url_field(inner)
        if url and "url" not in inner:
            inner = dict(inner)
            inner["url"] = url
            logger.debug("MCP 配置: URL 字段已标准化")

        return inner

    @classmethod
    def detect_transport_type(cls, config_json: dict) -> str:
        """
        根据 JSON 配置自动检测传输方式。

        检测规则：
        1. 包含 "command" 字段 -> stdio
        2. 包含 URL 字段：
           - type 为 streamable-http/streamableHttp/streamable_http -> streamable-http
           - type 为 sse 或无 type -> sse
        3. 无法识别 -> 抛出详细错误
        """
        try:
            inner = cls.normalize_config(config_json)
        except ValueError:
            raise

        # 检测 stdio
        if "command" in inner:
            logger.debug("MCP 配置: 检测到 stdio 传输类型")
            return "stdio"

        # 检测 HTTP 类型
        url = inner.get("url")
        if url:
            # 标准化 type 字段
            raw_type = inner.get("type", "")
            transport_type = cls._normalize_transport_type(raw_type) if raw_type else "sse"

            # 验证类型是否有效
            if transport_type not in ["stdio", "sse", "streamable-http"]:
                logger.warning(f"MCP 配置: 未知类型 '{raw_type}'，默认使用 sse")
                transport_type = "sse"

            logger.debug(f"MCP 配置: 检测到 {transport_type} 传输类型")
            return transport_type

        # 无法识别，提供详细错误信息
        available_fields = list(inner.keys())
        raise ValueError(
            f"无法识别 MCP 传输方式。\n"
            f"配置中的字段: {available_fields}\n"
            f"支持的格式:\n"
            f"  - stdio: 需包含 'command' 字段\n"
            f"  - sse/streamable-http: 需包含 'url'/'baseUrl'/'endpoint' 字段\n"
            f"示例:\n"
            f'  {{"command": "npx", "args": ["-y", "package"]}}\n'
            f'  {{"url": "https://...", "type": "sse"}}\n'
            f'  {{"url": "https://...", "type": "streamable-http"}}'
        )

    async def create_temp_client(self, config_json: dict, transport_type: str) -> BaseMCPClient:
        """创建临时客户端（用于连通性测试），不纳入连接池，调用方负责断开"""
        client = self._create_client(config_json, transport_type)
        await client.connect()
        return client
