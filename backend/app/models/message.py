from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Index, JSON
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT, "mysql"), nullable=False)
    token_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reasoning_content: Mapped[Optional[str]] = mapped_column(Text().with_variant(MEDIUMTEXT, "mysql"), nullable=True)

    # 消息树结构
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    branch_index: Mapped[int] = mapped_column(nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    # 消息引用
    referenced_message_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    tool_calls = relationship(
        "MessageToolCall", back_populates="message", lazy="selectin", cascade="all, delete-orphan"
    )
    children = relationship(
        "Message",
        backref=backref("parent", remote_side="Message.id"),
        lazy="noload",
    )

    __table_args__ = (
        Index("idx_conversation_time", "conversation_id", "created_at"),
        Index("idx_parent_branch", "parent_id", "branch_index"),
        Index("idx_conv_active", "conversation_id", "is_active"),
    )


class MessageToolCall(Base):
    __tablename__ = "message_tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    tool_call_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    arguments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    message = relationship("Message", back_populates="tool_calls")

    __table_args__ = (
        Index("idx_msgtc_message", "message_id"),
    )
