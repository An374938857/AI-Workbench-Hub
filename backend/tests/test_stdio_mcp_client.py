import asyncio
import os
import sys
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.mcp.stdio_client import StdioMCPClient


def test_stdio_client_disconnect_closes_context_in_runner_task(monkeypatch):
    state: dict[str, asyncio.Task | None] = {
        "transport_enter_task": None,
        "transport_exit_task": None,
        "session_enter_task": None,
        "session_exit_task": None,
    }

    class FakeTool:
        name = "ping"
        description = "pong"
        inputSchema = None

    class FakeListToolsResult:
        def __init__(self):
            self.tools = [FakeTool()]

    class FakeSession:
        def __init__(self, read_stream, write_stream):
            self._read_stream = read_stream
            self._write_stream = write_stream

        async def __aenter__(self):
            state["session_enter_task"] = asyncio.current_task()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            state["session_exit_task"] = asyncio.current_task()

        async def initialize(self):
            return None

        async def list_tools(self):
            return FakeListToolsResult()

    @asynccontextmanager
    async def fake_stdio_client(server_params, errlog=None):
        state["transport_enter_task"] = asyncio.current_task()
        try:
            yield object(), object()
        finally:
            state["transport_exit_task"] = asyncio.current_task()

    async def scenario():
        caller_task = asyncio.current_task()
        monkeypatch.setattr("app.services.mcp.stdio_client.stdio_client", fake_stdio_client)
        monkeypatch.setattr("app.services.mcp.stdio_client.ClientSession", FakeSession)

        client = StdioMCPClient(command="fake-mcp")
        await client.connect()
        tools = await client.list_tools()
        await client.disconnect()

        assert len(tools) == 1
        assert state["transport_enter_task"] is not None
        assert state["transport_enter_task"] == state["transport_exit_task"]
        assert state["session_enter_task"] == state["session_exit_task"]
        assert state["transport_enter_task"] != caller_task
        assert state["session_enter_task"] != caller_task

    asyncio.run(scenario())
