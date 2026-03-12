import types
import asyncio
import json
import os
import tempfile
from datetime import datetime


from app.models.message import Message, MessageToolCall
from app.models.conversation import Conversation
from app.services.conversation_execution import ConversationExecutionEngine


class FakeToolExecutor:
    async def execute(self, **kwargs):  # pragma: no cover
        raise NotImplementedError


class FakeToolExecutorWithFile:
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def execute(self, **kwargs):
        return types.SimpleNamespace(
            success=True,
            content=json.dumps({"data": {"filePath": self.file_path}}, ensure_ascii=False),
            error=None,
            response_time_ms=5,
        )


class FakeToolExecutorWithFileAndTitle:
    def __init__(self, file_path: str, title: str):
        self.file_path = file_path
        self.title = title

    async def execute(self, **kwargs):
        return types.SimpleNamespace(
            success=True,
            content=json.dumps(
                {"data": {"filePath": self.file_path, "title": self.title}},
                ensure_ascii=False,
            ),
            error=None,
            response_time_ms=5,
        )


class FakeToolExecutorCaptureArgs:
    def __init__(self):
        self.last_arguments = None

    async def execute(self, **kwargs):
        self.last_arguments = kwargs.get("arguments")
        return types.SimpleNamespace(
            success=True,
            content=json.dumps({"ok": True}, ensure_ascii=False),
            error=None,
            response_time_ms=5,
        )


class FakeToolExecutorWriteWorkMaster:
    async def execute(self, **kwargs):
        args = kwargs.get("arguments") or {}
        workspace = args.get("workspace")
        assert workspace, "workspace should be injected for this test"
        output_file = os.path.join(workspace, ".work-master", "from-work-master.md")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# from work-master")
        return types.SimpleNamespace(
            success=True,
            content=json.dumps({"ok": True}, ensure_ascii=False),
            error=None,
            response_time_ms=5,
        )


class FakeDB:
    def __init__(self):
        self._next_id = 1
        self.records = []

    def _assign_id(self, obj):
        if getattr(obj, "id", None) is None:
            setattr(obj, "id", self._next_id)
            self._next_id += 1

    def add(self, obj):
        self._assign_id(obj)
        self.records.append(obj)

    def flush(self):
        for obj in self.records:
            self._assign_id(obj)

    def commit(self):
        for obj in self.records:
            self._assign_id(obj)

    def refresh(self, obj):
        self._assign_id(obj)

    def query(self, *args, **kwargs):  # pragma: no cover - persist_logs=False path
        raise AssertionError("query() should not be called in these tests")


class _QueryStub:
    def __init__(self, item):
        self._item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._item


class _LiveStatusDBStub:
    def __init__(self, conv, msg):
        self.conv = conv
        self.msg = msg
        self.commits = 0

    def query(self, model):
        if model is Conversation:
            return _QueryStub(self.conv)
        if model is Message:
            return _QueryStub(self.msg)
        return _QueryStub(None)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        return obj


class FakeProviderNoTool:
    async def chat_completion_stream(self, **kwargs):
        yield {"type": "content_delta", "content": "hello "}
        yield {"type": "content_delta", "content": "world"}


class FakeProviderWithTool:
    def __init__(self):
        self.calls = 0

    async def chat_completion_stream(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield {
                "type": "tool_call",
                "tool_call": {
                    "id": "tool-1",
                    "type": "function",
                    "function": {"name": "1__read_file", "arguments": "{\"path\":\"/tmp/a.txt\"}"},
                },
            }
            return
        yield {"type": "content_delta", "content": "done after tool"}


class FakeProviderSkillActivationPause:
    def __init__(self):
        self.calls = 0

    async def chat_completion_stream(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield {
                "type": "tool_call",
                "tool_call": {
                    "id": "tool-1",
                    "type": "function",
                    "function": {"name": "activate_skill_7", "arguments": "{}"},
                },
            }
            return
        yield {"type": "content_delta", "content": "final response"}


def test_run_agent_loop_without_tool_calls():
    db = FakeDB()
    engine = ConversationExecutionEngine(db=db, user_id=1, tool_executor=FakeToolExecutor())
    events = []

    async def on_event(evt):
        events.append(evt)

    result = asyncio.run(
        engine.run_agent_loop(
            provider=FakeProviderNoTool(),
            context=[{"role": "user", "content": "hi"}],
            model_name="test-model",
            tools_param=None,
            tool_routing={},
            mcp_config_cache={},
            conversation_id=10,
            parent_message_id=100,
            on_event=on_event,
            persist_logs=False,
            persist_generated_files=False,
        )
    )

    assert result["content"] == "hello world"
    assert result["tool_rounds"] == 0
    assert any(evt["type"] == "chunk" for evt in events)
    assert events[-1]["type"] == "done"
    final_msgs = [r for r in db.records if isinstance(r, Message) and r.role == "assistant"]
    assert len(final_msgs) == 1
    assert final_msgs[0].content == "hello world"


def test_set_live_status_reactivates_inactive_live_message():
    conv = types.SimpleNamespace(
        id=33,
        live_status="running",
        live_message_id=None,
        live_error_message=None,
        live_stage=None,
        live_stage_detail=None,
        live_stage_meta_json=None,
        live_round_no=None,
        live_started_at=datetime.now(),
        live_updated_at=datetime.now(),
        sidebar_signal_state="none",
        sidebar_signal_updated_at=None,
        sidebar_signal_read_at=None,
    )
    msg = types.SimpleNamespace(
        id=88,
        conversation_id=33,
        is_active=False,
    )
    db = _LiveStatusDBStub(conv=conv, msg=msg)
    engine = ConversationExecutionEngine(db=db, user_id=1, tool_executor=FakeToolExecutor())

    engine.set_live_status(
        33,
        status="idle",
        message_id=88,
        commit=False,
    )

    assert conv.live_message_id == 88
    assert msg.is_active is True


def test_run_agent_loop_with_tool_call_roundtrip():
    db = FakeDB()
    engine = ConversationExecutionEngine(db=db, user_id=1, tool_executor=FakeToolExecutor())
    events = []

    async def on_event(evt):
        events.append(evt)

    async def fake_execute_tool_call(self, **kwargs):
        return {"content": "file content", "_success": True, "files": []}

    engine._execute_tool_call = types.MethodType(fake_execute_tool_call, engine)

    result = asyncio.run(
        engine.run_agent_loop(
            provider=FakeProviderWithTool(),
            context=[{"role": "user", "content": "please use tool"}],
            model_name="test-model",
            tools_param=[{"type": "function", "function": {"name": "1__read_file", "parameters": {"type": "object"}}}],
            tool_routing={"1__read_file": {"display_name": "read_file"}},
            mcp_config_cache={},
            conversation_id=11,
            parent_message_id=101,
            on_event=on_event,
            persist_logs=False,
            persist_generated_files=False,
        )
    )

    assert result["content"] == "done after tool"
    assert result["tool_rounds"] == 1
    assert any(evt["type"] == "tool_call_start" for evt in events)
    assert any(evt["type"] == "tool_call_result" for evt in events)
    tool_msgs = [r for r in db.records if isinstance(r, Message) and r.role == "tool"]
    assert len(tool_msgs) == 1
    tool_calls = [r for r in db.records if isinstance(r, MessageToolCall)]
    assert len(tool_calls) == 1


def test_run_agent_loop_pauses_after_skill_activation_request():
    db = FakeDB()
    engine = ConversationExecutionEngine(db=db, user_id=1, tool_executor=FakeToolExecutor())
    events = []
    execute_count = {"count": 0}

    async def on_event(evt):
        events.append(evt)

    async def fake_execute_tool_call(self, **kwargs):
        execute_count["count"] += 1
        return {
            "content": "{}",
            "_success": True,
            "_skill_activation": {
                "skill_id": 7,
                "skill_name": "会议纪要",
                "skill_description": "会议纪要技能",
            },
            "files": [],
        }

    engine._execute_tool_call = types.MethodType(fake_execute_tool_call, engine)

    result = asyncio.run(
        engine.run_agent_loop(
            provider=FakeProviderSkillActivationPause(),
            context=[{"role": "user", "content": "帮我写会议纪要"}],
            model_name="test-model",
            tools_param=[{"type": "function", "function": {"name": "activate_skill_7", "parameters": {"type": "object"}}}],
            tool_routing={},
            mcp_config_cache={},
            conversation_id=12,
            parent_message_id=102,
            on_event=on_event,
            persist_logs=False,
            persist_generated_files=False,
        )
    )

    assert result["content"] == ""
    assert execute_count["count"] == 1
    assert result["waiting_for_skill_confirmation"] is True
    assert any(evt.get("type") == "skill_activation_request" for evt in events)
    assert events[-1]["type"] == "done"
    assert events[-1]["waiting_for_skill_confirmation"] is True
    tool_msgs = [r for r in db.records if isinstance(r, Message) and r.role == "tool"]
    assert len(tool_msgs) == 1
    assert "skill_activation_pending" in tool_msgs[0].content


def test_execute_tool_call_rewrites_absolute_file_path_to_sandbox_path():
    db = FakeDB()
    with tempfile.TemporaryDirectory() as tmpdir:
        source_root = os.path.join(tmpdir, ".work-master")
        os.makedirs(source_root, exist_ok=True)
        source_file = os.path.join(source_root, "from-mcp.md")
        with open(source_file, "w", encoding="utf-8") as f:
            f.write("# generated from mcp")

        engine = ConversationExecutionEngine(
            db=db,
            user_id=1,
            tool_executor=FakeToolExecutorWithFile(source_file),
        )
        engine.settings = types.SimpleNamespace(UPLOAD_DIR=os.path.join(tmpdir, "uploads"))

        tc = {
            "id": "tool-file-1",
            "function": {"name": "1__download_doc", "arguments": "{}"},
        }
        route_info = {
            "mcp_id": 1,
            "tool_name": "download_doc",
            "timeout_seconds": 30,
            "max_retries": 1,
            "circuit_breaker_threshold": 5,
            "circuit_breaker_recovery": 300,
        }

        result = asyncio.run(
            engine._execute_tool_call(
                tc=tc,
                route_info=route_info,
                mcp_config_cache={1: ({}, "stdio")},
                conversation_id=493,
                assistant_msg_id=None,
                persist_logs=False,
                persist_generated_files=True,
            )
        )

        payload = json.loads(result["content"])
        assert payload["data"]["filePath"] == "generated/from-mcp.md"
        assert os.path.exists(
            os.path.join(tmpdir, "uploads", "sandbox", "493", "generated", "from-mcp.md")
        )
        assert not os.path.exists(source_file)


def test_execute_tool_call_uses_title_as_generated_filename():
    db = FakeDB()
    with tempfile.TemporaryDirectory() as tmpdir:
        source_root = os.path.join(tmpdir, ".work-master")
        os.makedirs(source_root, exist_ok=True)
        source_file = os.path.join(source_root, "tmp_1741512345_abcd.md")
        with open(source_file, "w", encoding="utf-8") as f:
            f.write("# generated from mcp")

        engine = ConversationExecutionEngine(
            db=db,
            user_id=1,
            tool_executor=FakeToolExecutorWithFileAndTitle(source_file, "业务文档A"),
        )
        engine.settings = types.SimpleNamespace(UPLOAD_DIR=os.path.join(tmpdir, "uploads"))

        tc = {
            "id": "tool-file-3",
            "function": {"name": "1__download_doc", "arguments": "{}"},
        }
        route_info = {
            "mcp_id": 1,
            "tool_name": "download_doc",
            "timeout_seconds": 30,
            "max_retries": 1,
            "circuit_breaker_threshold": 5,
            "circuit_breaker_recovery": 300,
        }

        result = asyncio.run(
            engine._execute_tool_call(
                tc=tc,
                route_info=route_info,
                mcp_config_cache={1: ({}, "stdio")},
                conversation_id=495,
                assistant_msg_id=None,
                persist_logs=False,
                persist_generated_files=True,
            )
        )

        payload = json.loads(result["content"])
        assert payload["data"]["filePath"] == "generated/业务文档A.md"
        assert os.path.exists(
            os.path.join(tmpdir, "uploads", "sandbox", "495", "generated", "业务文档A.md")
        )
        assert not os.path.exists(source_file)


def test_execute_tool_call_skips_confirmation_for_already_active_skill():
    db = FakeDB()
    engine = ConversationExecutionEngine(db=db, user_id=1, tool_executor=FakeToolExecutor())

    from app.services.skill_activation_manager import SkillActivationManager

    original_get_active_skills = SkillActivationManager.get_active_skills
    try:
        SkillActivationManager.get_active_skills = staticmethod(
            lambda conversation_id, _db, user_id: [
                {"id": 7, "name": "PRD 评审专家", "brief_desc": "PRD 评审"}
            ]
        )
        result = asyncio.run(
            engine._execute_tool_call(
                tc={
                    "id": "tool-skill-1",
                    "function": {"name": "activate_skill_7", "arguments": "{}"},
                },
                route_info=None,
                mcp_config_cache={},
                conversation_id=501,
                assistant_msg_id=None,
                persist_logs=False,
                persist_generated_files=False,
            )
        )
    finally:
        SkillActivationManager.get_active_skills = original_get_active_skills

    payload = json.loads(result["content"])
    assert result["_success"] is True
    assert payload["type"] == "skill_already_active"
    assert payload["skill_id"] == 7
    assert "无需重复确认" in payload["message"]
    assert "_skill_activation" not in result


def test_execute_tool_call_prefers_sandbox_output_dir_from_input_schema():
    db = FakeDB()
    with tempfile.TemporaryDirectory() as tmpdir:
        capture_executor = FakeToolExecutorCaptureArgs()
        engine = ConversationExecutionEngine(
            db=db,
            user_id=1,
            tool_executor=capture_executor,
        )
        engine.settings = types.SimpleNamespace(UPLOAD_DIR=os.path.join(tmpdir, "uploads"))

        tc = {
            "id": "tool-file-2",
            "function": {"name": "1__download_doc", "arguments": "{}"},
        }
        route_info = {
            "mcp_id": 1,
            "tool_name": "download_doc",
            "input_schema": {
                "type": "object",
                "properties": {
                    "output_dir": {"type": "string"},
                    "outputPath": {"type": "string"},
                    "workspace": {"type": "string"},
                },
            },
            "timeout_seconds": 30,
            "max_retries": 1,
            "circuit_breaker_threshold": 5,
            "circuit_breaker_recovery": 300,
        }

        result = asyncio.run(
            engine._execute_tool_call(
                tc=tc,
                route_info=route_info,
                mcp_config_cache={1: ({}, "stdio")},
                conversation_id=494,
                assistant_msg_id=None,
                persist_logs=False,
                persist_generated_files=False,
            )
        )

        assert result["_success"] is True
        assert capture_executor.last_arguments is not None
        assert capture_executor.last_arguments["output_dir"] == os.path.join(
            tmpdir, "uploads", "sandbox", "494", "generated"
        )
        assert capture_executor.last_arguments["outputPath"] == os.path.join(
            tmpdir, "uploads", "sandbox", "494", "generated"
        )
        assert capture_executor.last_arguments["workspace"] == os.path.join(
            tmpdir, "uploads", "sandbox", "494"
        )


def test_execute_tool_call_collects_and_moves_sandbox_work_master_files():
    db = FakeDB()
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ConversationExecutionEngine(
            db=db,
            user_id=1,
            tool_executor=FakeToolExecutorWriteWorkMaster(),
        )
        engine.settings = types.SimpleNamespace(UPLOAD_DIR=os.path.join(tmpdir, "uploads"))

        tc = {
            "id": "tool-file-4",
            "function": {"name": "1__generate_doc", "arguments": "{}"},
        }
        route_info = {
            "mcp_id": 1,
            "tool_name": "generate_doc",
            "input_schema": {
                "type": "object",
                "properties": {
                    "workspace": {"type": "string"},
                },
            },
            "timeout_seconds": 30,
            "max_retries": 1,
            "circuit_breaker_threshold": 5,
            "circuit_breaker_recovery": 300,
        }

        result = asyncio.run(
            engine._execute_tool_call(
                tc=tc,
                route_info=route_info,
                mcp_config_cache={1: ({}, "stdio")},
                conversation_id=496,
                assistant_msg_id=None,
                persist_logs=False,
                persist_generated_files=True,
            )
        )

        assert result["_success"] is True
        generated_file = os.path.join(
            tmpdir, "uploads", "sandbox", "496", "generated", "from-work-master.md"
        )
        sandbox_work_master_file = os.path.join(
            tmpdir, "uploads", "sandbox", "496", ".work-master", "from-work-master.md"
        )
        assert os.path.exists(generated_file)
        assert not os.path.exists(sandbox_work_master_file)


def test_execute_tool_call_rewrites_upload_to_yuque_relative_file_path():
    db = FakeDB()
    with tempfile.TemporaryDirectory() as tmpdir:
        capture_executor = FakeToolExecutorCaptureArgs()
        engine = ConversationExecutionEngine(
            db=db,
            user_id=1,
            tool_executor=capture_executor,
        )
        engine.settings = types.SimpleNamespace(UPLOAD_DIR=os.path.join(tmpdir, "uploads"))

        conversation_id = 552
        sandbox_file = os.path.join(
            tmpdir,
            "uploads",
            "sandbox",
            str(conversation_id),
            "prd-output",
            "demo.md",
        )
        os.makedirs(os.path.dirname(sandbox_file), exist_ok=True)
        with open(sandbox_file, "w", encoding="utf-8") as f:
            f.write("# demo")

        tc = {
            "id": "tool-file-5",
            "function": {
                "name": "5__upload_to_yuque",
                "arguments": json.dumps(
                    {
                        "teamId": "hb3fga",
                        "repoId": "newbie",
                        "title": "demo",
                        "filePath": "prd-output/demo.md",
                    },
                    ensure_ascii=False,
                ),
            },
        }
        route_info = {
            "mcp_id": 5,
            "tool_name": "upload_to_yuque",
            "timeout_seconds": 30,
            "max_retries": 1,
            "circuit_breaker_threshold": 5,
            "circuit_breaker_recovery": 300,
        }

        result = asyncio.run(
            engine._execute_tool_call(
                tc=tc,
                route_info=route_info,
                mcp_config_cache={5: ({}, "stdio")},
                conversation_id=conversation_id,
                assistant_msg_id=None,
                persist_logs=False,
                persist_generated_files=False,
            )
        )

        assert result["_success"] is True
        assert capture_executor.last_arguments is not None
        assert capture_executor.last_arguments["filePath"] == sandbox_file
