import json
import time
from typing import Any, AsyncIterator, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.services.llm.base import BaseLLMProvider


class OpenAICompatibleProvider(BaseLLMProvider):

    def __init__(self, api_base_url: str, api_key: str):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _dashscope_multimodal_endpoint(self) -> Optional[str]:
        parsed = urlparse(self.api_base_url)
        if "dashscope.aliyuncs.com" not in parsed.netloc:
            return None
        return (
            f"{parsed.scheme}://{parsed.netloc}"
            "/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"
        )

    @staticmethod
    def _is_embedding_model(model: str) -> bool:
        return "embedding" in (model or "").lower()

    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
    ) -> AsyncIterator[dict]:
        body: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.api_base_url}/chat/completions",
                json=body,
                headers=self._headers(),
            ) as response:
                if response.status_code != 200:
                    error_text = ""
                    async for chunk in response.aiter_text():
                        error_text += chunk
                    raise Exception(f"LLM API 错误 (HTTP {response.status_code}): {error_text[:200]}")

                tool_calls_acc: dict[int, dict] = {}
                reasoning_content_acc = ""
                reasoning_done_sent = False

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choice = chunk_data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason")

                    # 捕获 reasoning_content（DeepSeek Reasoner 思考模式）— 流式 yield
                    rc = delta.get("reasoning_content")
                    if rc:
                        reasoning_content_acc += rc
                        yield {"type": "reasoning_content_delta", "content": rc}

                    content = delta.get("content")
                    # 当 reasoning 结束后首次收到 content 或 finish_reason，发送 done 信号
                    if reasoning_content_acc and not reasoning_done_sent and (content or finish_reason):
                        reasoning_done_sent = True
                        yield {"type": "reasoning_content_done"}

                    if content:
                        yield {"type": "content_delta", "content": content}

                    if "tool_calls" in delta:
                        for tc_delta in delta["tool_calls"]:
                            idx = tc_delta["index"]
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            acc = tool_calls_acc[idx]
                            if tc_delta.get("id"):
                                acc["id"] = tc_delta["id"]
                            func_delta = tc_delta.get("function", {})
                            if func_delta.get("name"):
                                acc["function"]["name"] += func_delta["name"]
                            if func_delta.get("arguments"):
                                acc["function"]["arguments"] += func_delta["arguments"]

                    if finish_reason and tool_calls_acc:
                        for idx in sorted(tool_calls_acc.keys()):
                            yield {"type": "tool_call", "tool_call": tool_calls_acc[idx]}
                        if reasoning_content_acc:
                            yield {"type": "reasoning_content", "reasoning_content": reasoning_content_acc}
                            reasoning_content_acc = ""
                        tool_calls_acc.clear()

                    usage = chunk_data.get("usage")
                    if usage:
                        yield {"type": "usage", "usage": usage}

    async def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, dict]:
        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.api_base_url}/chat/completions",
                json=body,
                headers=self._headers(),
            )
            if resp.status_code != 200:
                raise Exception(f"LLM API 错误 (HTTP {resp.status_code}): {resp.text[:200]}")

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return content, usage

    async def test_connection(self, model: str) -> Tuple[bool, str, int]:
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if self._is_embedding_model(model):
                    resp = await client.post(
                        f"{self.api_base_url}/embeddings",
                        json={"model": model, "input": ["hi"]},
                        headers=self._headers(),
                    )
                else:
                    resp = await client.post(
                        f"{self.api_base_url}/chat/completions",
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

    async def create_embeddings(
        self,
        model: str,
        inputs: list[str],
    ) -> list[list[float]]:
        if not inputs:
            return []

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.api_base_url}/embeddings",
                json={"model": model, "input": inputs},
                headers=self._headers(),
            )
        if resp.status_code != 200:
            raise Exception(f"Embedding API 错误 (HTTP {resp.status_code}): {resp.text[:200]}")

        data = resp.json().get("data") or []
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        return [list(item.get("embedding") or []) for item in ordered]

    async def create_multimodal_embeddings(
        self,
        model: str,
        inputs: list[dict[str, Any]],
    ) -> list[list[float]]:
        if not inputs:
            return []

        dashscope_endpoint = self._dashscope_multimodal_endpoint()
        if dashscope_endpoint:
            async with httpx.AsyncClient(timeout=120.0) as client:
                vectors: list[list[float]] = []
                for item in inputs:
                    resp = await client.post(
                        dashscope_endpoint,
                        json={"model": model, "input": {"contents": [item]}},
                        headers=self._headers(),
                    )
                    if resp.status_code != 200:
                        raise Exception(f"多模态 Embedding API 错误 (HTTP {resp.status_code}): {resp.text[:300]}")

                    output = resp.json().get("output") or {}
                    embeddings = output.get("embeddings") or []
                    if not embeddings:
                        raise Exception("多模态 Embedding API 未返回 embeddings")
                    vectors.append(list(embeddings[0].get("embedding") or []))
                return vectors

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.api_base_url}/embeddings",
                    json={"model": model, "input": inputs},
                    headers=self._headers(),
                )
            if resp.status_code == 200:
                data = resp.json().get("data") or []
                ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
                return [list(item.get("embedding") or []) for item in ordered]
        except Exception:
            pass

        normalized = [json.dumps(item, ensure_ascii=False) for item in inputs]
        return await self.create_embeddings(model, normalized)
