"""模型对比模式数据模型"""
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModelComparison(Base):
    """模型对比记录"""
    __tablename__ = "model_comparisons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    model_a_provider_id: Mapped[int] = mapped_column(nullable=False)
    model_a_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_a_message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    model_b_provider_id: Mapped[int] = mapped_column(nullable=False)
    model_b_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_b_message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    winner: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 'a', 'b', or null
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_comparison_conv", "conversation_id", "created_at"),
    )
