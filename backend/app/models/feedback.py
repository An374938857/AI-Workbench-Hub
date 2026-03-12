from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    skill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("skills.id"), nullable=True)
    rating: Mapped[int] = mapped_column(nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    user = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("idx_feedback_skill", "skill_id"),
        Index("idx_feedback_conversation", "conversation_id"),
    )
