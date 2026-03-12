from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional, Tuple


class BaseLLMProvider(ABC):

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
    ) -> AsyncIterator[dict]:
        """
        流式对话，yield 事件字典：
        - {"type": "content_delta", "content": "文本"}
        - {"type": "tool_call", "tool_call": {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}}
        - {"type": "usage", "usage": {...}}
        当 tools=None 时行为与默认行为一致（仅产出 content_delta）。
        """
        ...

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, dict]:
        """非流式对话，返回 (完整回复, usage 信息)"""
        ...

    @abstractmethod
    async def test_connection(self, model: str) -> Tuple[bool, str, int]:
        """连通性测试，返回 (是否成功, 描述, 响应时间ms)"""
        ...

    async def create_embeddings(
        self,
        model: str,
        inputs: list[str],
    ) -> list[list[float]]:
        raise NotImplementedError("当前 provider 不支持 embeddings 接口")

    async def create_multimodal_embeddings(
        self,
        model: str,
        inputs: list[dict[str, Any]],
    ) -> list[list[float]]:
        normalized = [str(item.get("content") or item.get("text") or "") for item in inputs]
        return await self.create_embeddings(model, normalized)
