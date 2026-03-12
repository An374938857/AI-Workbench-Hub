import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.services.llm.openai_compatible import OpenAICompatibleProvider


class DummyResponse:
    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self):
        return self._payload


class DummyClient:
    def __init__(self, response: DummyResponse, recorder: dict):
        self.response = response
        self.recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, json, headers):
        self.recorder.setdefault("calls", []).append({"url": url, "json": json, "headers": headers})
        self.recorder["url"] = url
        self.recorder["json"] = json
        self.recorder["headers"] = headers
        return self.response


def test_dashscope_multimodal_embeddings_use_native_endpoint(monkeypatch):
    recorder: dict = {}
    response = DummyResponse(
        200,
        {
            "output": {
                "embeddings": [
                    {"embedding": [0.1, 0.2]},
                    {"embedding": [0.3, 0.4]},
                ]
            }
        },
    )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout=120.0: DummyClient(response, recorder),
    )

    provider = OpenAICompatibleProvider(
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "test-key",
    )
    vectors = asyncio.run(
        provider.create_multimodal_embeddings(
            "qwen3-vl-embedding",
            [{"text": "hello"}],
        )
    )

    assert recorder["url"].endswith("/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding")
    assert recorder["json"] == {
        "model": "qwen3-vl-embedding",
        "input": {"contents": [{"text": "hello"}]},
    }
    assert vectors == [[0.1, 0.2]]


def test_test_connection_uses_embeddings_endpoint_for_embedding_model(monkeypatch):
    recorder: dict = {}
    response = DummyResponse(200, {"data": [{"embedding": [0.1, 0.2], "index": 0}]})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout=30.0: DummyClient(response, recorder),
    )

    provider = OpenAICompatibleProvider(
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "test-key",
    )
    ok, detail, _elapsed = asyncio.run(provider.test_connection("text-embedding-v4"))

    assert ok is True
    assert detail == "连通正常"
    assert recorder["url"].endswith("/embeddings")
    assert recorder["json"] == {"model": "text-embedding-v4", "input": ["hi"]}
