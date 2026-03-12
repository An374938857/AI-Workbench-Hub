from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class MCPToolInfo:
    """MCP 工具信息"""
    name: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None


class BaseMCPClient(ABC):
    """MCP 客户端抽象基类"""

    @abstractmethod
    async def connect(self) -> None:
        """建立与 MCP 服务的连接并初始化会话"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接，清理资源"""
        ...

    @abstractmethod
    async def list_tools(self) -> list[MCPToolInfo]:
        """获取 MCP 服务提供的工具列表"""
        ...

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        执行工具调用。

        Args:
            tool_name: 工具名称
            arguments: 调用参数字典

        Returns:
            工具返回结果的文本内容

        Raises:
            ConnectionError: 连接断开
            TimeoutError: 调用超时
            Exception: 工具执行失败
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接是否存活"""
        ...
