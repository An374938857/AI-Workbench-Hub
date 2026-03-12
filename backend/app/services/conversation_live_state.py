import json

from app.models.conversation import Conversation
from app.services.conversation_sidebar_signal import serialize_sidebar_signal


def serialize_live_execution(conv: Conversation) -> dict:
    stage_meta = None
    if conv.live_stage_meta_json:
        try:
            parsed = json.loads(conv.live_stage_meta_json)
            stage_meta = parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            stage_meta = None

    return {
        "status": conv.live_status or "idle",
        "message_id": conv.live_message_id,
        "error_message": conv.live_error_message,
        "stage": conv.live_stage,
        "stage_detail": conv.live_stage_detail,
        "stage_meta": stage_meta,
        "round_no": conv.live_round_no,
        "started_at": conv.live_started_at.isoformat() if conv.live_started_at else None,
        "updated_at": conv.live_updated_at.isoformat() if conv.live_updated_at else None,
    }


def build_live_state_detail_version(conv: Conversation) -> str:
    """构建会话详情版本键，用于轻量轮询后判断是否需要补拉详情。"""
    status = conv.live_status or "idle"
    payload = {
        "status": status,
        "message_id": conv.live_message_id,
        "error_message": conv.live_error_message or None,
        "stage": conv.live_stage or None,
        "stage_detail": conv.live_stage_detail or None,
        "round_no": conv.live_round_no,
        "title": conv.title or "新对话",
        "active_skill_ids": conv.active_skill_ids or "",
        "current_provider_id": conv.current_provider_id,
        "current_model_name": conv.current_model_name,
        "sandbox_unread_change_count": int(conv.sandbox_unread_change_count or 0),
        "sidebar_signal_state": conv.sidebar_signal_state or "none",
        "sidebar_signal_updated_at": (
            conv.sidebar_signal_updated_at.isoformat()
            if conv.sidebar_signal_updated_at
            else None
        ),
        "sidebar_signal_read_at": (
            conv.sidebar_signal_read_at.isoformat()
            if conv.sidebar_signal_read_at
            else None
        ),
    }

    # 运行中不把 live_updated_at 纳入版本，避免因为流式落盘触发持续全量补拉。
    if status != "running":
        payload["live_updated_at"] = (
            conv.live_updated_at.isoformat() if conv.live_updated_at else None
        )
        payload["updated_at"] = conv.updated_at.isoformat() if conv.updated_at else None

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def serialize_live_state_snapshot(conv: Conversation) -> dict:
    return {
        "conversation_id": conv.id,
        "live_execution": serialize_live_execution(conv),
        "sidebar_signal": serialize_sidebar_signal(conv),
        "sandbox_unread_change_count": int(conv.sandbox_unread_change_count or 0),
        "detail_version": build_live_state_detail_version(conv),
    }
