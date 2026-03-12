from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PromptTemplateVersion(Base):
    """提示词模板版本表"""
    __tablename__ = "prompt_template_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("system_prompt_templates.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="personal")
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_ptv_template_version", "template_id", "version_no", unique=True),
        Index("idx_ptv_template_created", "template_id", "created_at"),
    )
