import json
import time
from typing import AsyncIterator, Optional, Tuple

import httpx

from app.services.llm.base import BaseLLMProvider


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Messages API 协议适配"""

    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, api_base_url: str, api_key: str):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    def _convert_messages(self, messages: list[dict]) -> Tuple[str, list[dict]]:
        """将平台统一格式转换为 Anthropic 格式：提取 system 为独立字段。

        Returns:
            (system_text, anthropic_messages)
        """
        system_parts: list[str] = []
        anthropic_messages: list[dict] = []

        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if content:
                    system_parts.append(content)
            else:
                anthropic_messages.append(msg)

        return "\n".join(system_parts), anthropic_messages

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """将 OpenAI 格式的 tools 转换为 Anthropic 格式。

        OpenAI format:
            {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        Anthropic format:
            {"name": ..., "description": ..., "input_schema": ...}
        """
        anthropic_tools = []
        for tool in tools:
            func = tool.get("function", {})
            anthropic_tool = {
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            }
            anthropic_tools.append(anthropic_tool)
        return anthropic_tools

    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
    ) -> AsyncIterator[dict]:
        system_text, anthropic_messages = self._convert_messages(messages)

        body: dict = {
            "model": model,
            "messages": anthropic_messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system_text:
            body["system"] = system_text
        if tools:
            body["tools"] = self._convert_tools(tools)

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.api_base_url}/v1/messages",
                json=body,
                headers=self._headers(),
            ) as response:
                if response.status_code != 200:
                    error_text = ""
                    async for chunk in response.aiter_text():
                        error_text += chunk
                    raise httpx.HTTPStatusError(
                        f"Anthropic API 错误 (HTTP {response.status_code}): {error_text[:200]}",
                        request=response.request,
                        response=response,
                    )

                # Track tool_use blocks being built
                current_tool: Optional[dict] = None
                tool_input_json = ""

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if not data_str:
                        continue
                    try:
                        event_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event_data.get("type", "")

                    if event_type == "content_block_start":
                        block = event_data.get("content_block", {})
                        if block.get("type") == "tool_use":
                            current_tool = {
                                "id": block.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": block.get("name", ""),
                                    "arguments": "",
                                },
                            }
                            tool_input_json = ""

                    elif event_type == "content_block_delta":
                        delta = event_data.get("delta", {})
                        delta_type = delta.get("type", "")

                        if delta_type == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield {"type": "content_delta", "content": text}

                        elif delta_type == "input_json_delta":
                            partial = delta.get("partial_json", "")
                            tool_input_json += partial

                    elif event_type == "content_block_stop":
                        if current_tool is not None:
                            current_tool["function"]["arguments"] = tool_input_json
                            yield {"type": "tool_call", "tool_call": current_tool}
                            current_tool = None
                            tool_input_json = ""

                    elif event_type == "message_delta":
                        usage = event_data.get("usage", {})
                        if usage:
                            yield {"type": "usage", "usage": usage}

                    elif event_type == "message_start":
                        msg = event_data.get("message", {})
                        usage = msg.get("usage", {})
                        if usage:
                            yield {"type": "usage", "usage": usage}

    async def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, dict]:
        system_text, anthropic_messages = self._convert_messages(messages)

        body: dict = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system_text:
            body["system"] = system_text

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.api_base_url}/v1/messages",
                json=body,
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"Anthropic API 错误 (HTTP {resp.status_code}): {resp.text[:200]}",
                    request=resp.request,
                    response=resp,
                )

            data = resp.json()
            # Extract text from content blocks
            content_parts = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content_parts.append(block.get("text", ""))
            content = "".join(content_parts)
            usage = data.get("usage", {})
            return content, usage

    async def test_connection(self, model: str) -> Tuple[bool, str, int]:
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.api_base_url}/v1/messages",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 5,
                    },
                    headers=self._headers(),
                )
            elapsed = int((time.time() - start) * 1000)
            if resp.status_code == 200:
                return True, "连通正常", elapsed
            return False, f"HTTP {resp.status_code}: {resp.text[:100]}", elapsed
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            return False, str(e)[:100], elapsed
