from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Index, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ModelProvider(Base):
    __tablename__ = "model_providers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    api_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    protocol_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="openai_compatible"
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_test_result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_test_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    models = relationship("ModelItem", back_populates="provider", lazy="selectin")


class ModelItem(Base):
    __tablename__ = "model_list"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("model_providers.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    context_window: Mapped[int] = mapped_column(nullable=False)
    is_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    capability_tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    speed_rating: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    cost_rating: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    max_output_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    provider = relationship("ModelProvider", back_populates="models")

    __table_args__ = (Index("idx_provider_enabled", "provider_id", "is_enabled"),)
