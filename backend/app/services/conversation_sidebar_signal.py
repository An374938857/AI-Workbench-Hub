from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.conversation import Conversation

SIDEBAR_SIGNAL_NONE = "none"
SIDEBAR_SIGNAL_RUNNING = "running"
SIDEBAR_SIGNAL_UNREAD_REPLY = "unread_reply"
SIDEBAR_SIGNAL_ERROR = "error"
SIDEBAR_SIGNAL_CANCELLED = "cancelled"
SIDEBAR_SIGNAL_WAITING_SKILL_CONFIRMATION = "waiting_skill_confirmation"

VALID_SIDEBAR_SIGNAL_STATES = {
    SIDEBAR_SIGNAL_NONE,
    SIDEBAR_SIGNAL_RUNNING,
    SIDEBAR_SIGNAL_UNREAD_REPLY,
    SIDEBAR_SIGNAL_ERROR,
    SIDEBAR_SIGNAL_CANCELLED,
    SIDEBAR_SIGNAL_WAITING_SKILL_CONFIRMATION,
}


def serialize_sidebar_signal(conv: Conversation) -> dict:
    return {
        "state": conv.sidebar_signal_state or SIDEBAR_SIGNAL_NONE,
        "updated_at": conv.sidebar_signal_updated_at.isoformat()
        if conv.sidebar_signal_updated_at
        else None,
        "read_at": conv.sidebar_signal_read_at.isoformat()
        if conv.sidebar_signal_read_at
        else None,
    }


def set_sidebar_signal(
    db: Session,
    conversation_id: int,
    state: str,
    *,
    event_time: Optional[datetime] = None,
    commit: bool = True,
) -> Optional[Conversation]:
    if state not in VALID_SIDEBAR_SIGNAL_STATES:
        raise ValueError(f"invalid sidebar signal state: {state}")
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return None
    apply_sidebar_signal(conv, state=state, event_time=event_time)
    if commit:
        db.commit()
    return conv


def apply_sidebar_signal(
    conv: Conversation,
    *,
    state: str,
    event_time: Optional[datetime] = None,
) -> None:
    if state not in VALID_SIDEBAR_SIGNAL_STATES:
        raise ValueError(f"invalid sidebar signal state: {state}")
    now = event_time or datetime.now()
    conv.sidebar_signal_state = state
    conv.sidebar_signal_updated_at = now
    if state != SIDEBAR_SIGNAL_NONE:
        # 新事件重亮语义：非 none 状态写入时清空 read_at，等待用户再次查看
        conv.sidebar_signal_read_at = None


def mark_sidebar_signal_read(
    db: Session,
    conversation_id: int,
    *,
    read_time: Optional[datetime] = None,
    commit: bool = True,
) -> Optional[Conversation]:
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return None
    apply_sidebar_signal_read(conv, read_time=read_time)
    if commit:
        db.commit()
    return conv


def apply_sidebar_signal_read(
    conv: Conversation,
    *,
    read_time: Optional[datetime] = None,
) -> None:
    now = read_time or datetime.now()
    if conv.sidebar_signal_state != SIDEBAR_SIGNAL_NONE:
        conv.sidebar_signal_state = SIDEBAR_SIGNAL_NONE
        conv.sidebar_signal_updated_at = now
    elif conv.sidebar_signal_updated_at is None:
        conv.sidebar_signal_updated_at = now
    if conv.sidebar_signal_read_at is None or conv.sidebar_signal_read_at < now:
        conv.sidebar_signal_read_at = now
