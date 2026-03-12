import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.conversation_live_state import (  # noqa: E402
    build_live_state_detail_version,
    serialize_live_execution,
    serialize_live_state_snapshot,
)


def make_conversation(**overrides):
    base_time = datetime(2026, 3, 9, 20, 0, 0)
    payload = {
        "id": 101,
        "title": "测试对话",
        "active_skill_ids": '{"skill_ids":[1,2]}',
        "current_provider_id": 8,
        "current_model_name": "gpt-test",
        "sandbox_unread_change_count": 0,
        "live_status": "idle",
        "live_message_id": 2001,
        "live_error_message": None,
        "live_stage": None,
        "live_stage_detail": None,
        "live_stage_meta_json": None,
        "live_round_no": None,
        "live_started_at": base_time,
        "live_updated_at": base_time,
        "sidebar_signal_state": "none",
        "sidebar_signal_updated_at": None,
        "sidebar_signal_read_at": None,
        "updated_at": base_time,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_running_detail_version_ignores_live_updated_at_changes():
    conv = make_conversation(live_status="running")
    version_a = build_live_state_detail_version(conv)

    conv.live_updated_at = conv.live_updated_at + timedelta(seconds=5)
    conv.updated_at = conv.updated_at + timedelta(seconds=5)
    version_b = build_live_state_detail_version(conv)

    assert version_a == version_b


def test_terminal_detail_version_changes_when_live_updated_at_changes():
    conv = make_conversation(live_status="idle")
    version_a = build_live_state_detail_version(conv)

    conv.live_updated_at = conv.live_updated_at + timedelta(seconds=1)
    version_b = build_live_state_detail_version(conv)

    assert version_a != version_b


def test_detail_version_changes_when_title_changes():
    conv = make_conversation(live_status="running")
    version_a = build_live_state_detail_version(conv)

    conv.title = "新的标题"
    version_b = build_live_state_detail_version(conv)

    assert version_a != version_b


def test_live_state_snapshot_contains_serialized_execution_and_version():
    conv = make_conversation(
        live_status="error",
        live_error_message="调用失败",
        live_started_at=datetime(2026, 3, 9, 19, 55, 0),
    )

    snapshot = serialize_live_state_snapshot(conv)

    assert snapshot["conversation_id"] == conv.id
    assert snapshot["live_execution"] == serialize_live_execution(conv)
    assert snapshot["sidebar_signal"]["state"] == "none"
    assert snapshot["detail_version"] == build_live_state_detail_version(conv)
    assert snapshot["sandbox_unread_change_count"] == 0
    assert snapshot["live_execution"]["status"] == "error"
    assert snapshot["live_execution"]["error_message"] == "调用失败"


def test_serialize_live_execution_includes_persisted_progress_fields():
    conv = make_conversation(
        live_status="running",
        live_message_id=2222,
        live_stage="tool_running",
        live_stage_detail="正在调用工具：knowledge_search",
        live_stage_meta_json='{"tool_name":"knowledge_search","phase":"tool"}',
        live_round_no=2,
    )

    payload = serialize_live_execution(conv)

    assert payload["status"] == "running"
    assert payload["message_id"] == 2222
    assert payload["stage"] == "tool_running"
    assert payload["stage_detail"] == "正在调用工具：knowledge_search"
    assert payload["round_no"] == 2
    assert payload["stage_meta"] == {"tool_name": "knowledge_search", "phase": "tool"}
