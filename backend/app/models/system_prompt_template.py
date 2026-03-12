from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SystemPromptTemplate(Base):
    """系统提示词模板表"""
    __tablename__ = "system_prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="role")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="personal")
    is_global_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        Index("idx_template_category", "category"),
        Index("idx_template_visibility", "visibility"),
        Index("idx_template_global_default", "is_global_default"),
    )