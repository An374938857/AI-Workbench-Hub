from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.conversation import Conversation


def increase_sandbox_unread_change_count(
    db: Session,
    conversation_id: int,
    *,
    delta: int = 1,
) -> int:
    if delta <= 0:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        return int(conv.sandbox_unread_change_count or 0) if conv else 0

    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return 0
    conv.sandbox_unread_change_count = int(conv.sandbox_unread_change_count or 0) + int(delta)
    return conv.sandbox_unread_change_count


def reset_sandbox_unread_change_count(db: Session, conversation_id: int) -> int:
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return 0
    conv.sandbox_unread_change_count = 0
    return 0
