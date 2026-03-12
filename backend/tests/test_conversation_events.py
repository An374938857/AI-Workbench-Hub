import os
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.conversation_events import (  # noqa: E402
    ConversationEventVersionGenerator,
    build_conversation_sync_event,
    get_conversation_event_channel,
)


def make_conversation(**overrides):
    now = datetime(2026, 3, 11, 12, 0, 0)
    payload = {
        "id": 532,
        "user_id": 1001,
        "title": "测试会话",
        "live_status": "running",
        "live_message_id": 901,
        "live_error_message": None,
        "live_stage": "llm_streaming",
        "live_stage_detail": "模型正在生成回复（第 2 轮）",
        "live_stage_meta_json": '{"phase":"llm"}',
        "live_round_no": 2,
        "live_started_at": now,
        "live_updated_at": now,
        "sandbox_unread_change_count": 2,
        "sidebar_signal_state": "running",
        "sidebar_signal_updated_at": now,
        "sidebar_signal_read_at": None,
        "active_skill_ids": "{}",
        "current_provider_id": 1,
        "current_model_name": "gpt-test",
        "updated_at": now,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_get_conversation_event_channel_is_user_scoped():
    assert get_conversation_event_channel(7) == "conversation_events:user:7"


def test_version_generator_is_monotonic_for_same_conversation():
    generator = ConversationEventVersionGenerator()
    v1 = generator.next_version(532)
    v2 = generator.next_version(532)
    assert isinstance(v1, int)
    assert isinstance(v2, int)
    assert v2 > v1


def test_build_conversation_sync_event_contains_minimal_contract_fields():
    conv = make_conversation()

    event = build_conversation_sync_event(
        conv=conv,
        event_type="conversation.live_state_changed",
        event_version=123456,
    )

    assert event["type"] == "conversation.live_state_changed"
    assert event["conversation_id"] == 532
    assert event["event_version"] == 123456
    assert event["event_ts"]

    patch = event["patch"]
    assert patch["title"] == "测试会话"
    assert patch["sandbox_unread_change_count"] == 2
    assert patch["live_execution"]["status"] == "running"
    assert patch["live_execution"]["stage"] == "llm_streaming"
    assert patch["live_execution"]["stage_detail"] == "模型正在生成回复（第 2 轮）"
    assert patch["live_execution"]["round_no"] == 2
    assert patch["live_execution"]["stage_meta"] == {"phase": "llm"}
    assert patch["sidebar_signal"]["state"] == "running"
    assert isinstance(patch["detail_version"], str)
