from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    skill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("skills.id"), nullable=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False
    )
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("model_providers.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    is_success: Mapped[bool] = mapped_column(nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_user_time", "user_id", "created_at"),
        Index("idx_skill_time", "skill_id", "created_at"),
        Index("idx_provider_time", "provider_id", "created_at"),
    )
