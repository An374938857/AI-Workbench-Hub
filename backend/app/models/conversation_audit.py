from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, JSON
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConversationAuditTrace(Base):
    __tablename__ = "conversation_audit_traces"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    is_abnormal: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    abnormal_types: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_cat_conv_time", "conversation_id", "started_at"),
        Index("idx_cat_user_time", "user_id", "started_at"),
        Index("idx_cat_abnormal_time", "is_abnormal", "started_at"),
    )


class ConversationAuditEvent(Base):
    __tablename__ = "conversation_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    round_no: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_raw: Mapped[str] = mapped_column(Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verify_status: Mapped[str] = mapped_column(String(16), nullable=False, default="passed", server_default="passed")
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_cae_trace_time", "trace_id", "event_time"),
        Index("idx_cae_conv_round", "conversation_id", "round_no"),
        Index("idx_cae_type_time", "event_type", "event_time"),
        Index("idx_cae_verify_time", "verify_status", "event_time"),
    )


class ConversationAuditArchive(Base):
    __tablename__ = "conversation_audit_archives"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    archive_batch_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    archive_date: Mapped[date] = mapped_column(Date, nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    record_count: Mapped[int] = mapped_column(nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=datetime.now)
