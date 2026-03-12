from datetime import datetime
from typing import Optional
from sqlalchemy import JSON, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    intent_category: Mapped[str] = mapped_column(String(50), nullable=False, comment="意图类别，如 coding/creative_writing")
    display_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="中文显示名")
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, comment="关键词列表")
    preferred_tags: Mapped[list] = mapped_column(JSON, nullable=False, comment="首选能力标签列表")
    preferred_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="首选模型 provider_id:model_name")
    priority: Mapped[int] = mapped_column(nullable=False, default=0, comment="优先级，越大越优先")
    is_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (Index("idx_routing_rule_enabled", "is_enabled", "priority"),)
