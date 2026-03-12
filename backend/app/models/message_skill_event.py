from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MessageSkillEvent(Base):
    """消息层技能事件（会话技能状态的唯一事实来源）。"""

    __tablename__ = "message_skill_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    is_manual_preferred: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    __table_args__ = (
        Index(
            "idx_mse_conv_time",
            "conversation_id",
            "created_at",
            "id",
        ),
        Index("idx_mse_conv_skill", "conversation_id", "skill_id"),
        Index("idx_mse_message", "message_id"),
    )

