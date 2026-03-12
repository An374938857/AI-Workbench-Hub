from datetime import datetime

from sqlalchemy import Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserPromptFavorite(Base):
    """用户提示词模板收藏表"""
    __tablename__ = "user_prompt_favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    template_id: Mapped[int] = mapped_column(ForeignKey("system_prompt_templates.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_favorite_user_template", "user_id", "template_id", unique=True),
    )