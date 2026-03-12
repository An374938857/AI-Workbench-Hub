"""Fallback 配置和日志模型"""
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModelFallbackConfig(Base):
    """模型 Fallback 配置"""
    __tablename__ = "model_fallback_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_provider_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_providers.id", ondelete="CASCADE"), nullable=True
    )
    source_model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fallback_chain: Mapped[list] = mapped_column(JSON, nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        Index("idx_fallback_source", "source_provider_id", "source_model_name"),
    )


class ModelFallbackLog(Base):
    """模型 Fallback 日志"""
    __tablename__ = "model_fallback_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    original_provider_id: Mapped[int] = mapped_column(nullable=False)
    original_model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fallback_provider_id: Mapped[int] = mapped_column(nullable=False)
    fallback_model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    error_type: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_fallback_log_conv", "conversation_id", "created_at"),
        Index("idx_fallback_log_model", "original_provider_id", "original_model_name"),
    )
