from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)  # PROJECT/REQUIREMENT
    scope_id: Mapped[int] = mapped_column(nullable=False)
    node_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)  # FILE/MARKDOWN/URL/YUQUE_URL
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    file_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    snapshot_markdown: Mapped[Optional[str]] = mapped_column(
        Text().with_variant(mysql.LONGTEXT(), "mysql"),
        nullable=True,
    )
    refetch_status: Mapped[str] = mapped_column(String(16), nullable=False, default="IDLE", server_default="IDLE")
    last_refetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    __table_args__ = (
        Index("idx_asset_scope", "scope_type", "scope_id"),
        Index("idx_asset_scope_node", "scope_type", "scope_id", "node_code"),
        Index("idx_asset_type", "asset_type"),
    )
