from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Index, JSON, Column, Table, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

skill_mcps = Table(
    "skill_mcps",
    Base.metadata,
    Column("skill_version_id", Integer, ForeignKey("skill_versions.id", ondelete="CASCADE"), primary_key=True),
    Column("mcp_id", Integer, ForeignKey("mcps.id", ondelete="CASCADE"), primary_key=True),
)


class Mcp(Base):
    __tablename__ = "mcps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    config_json_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    transport_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=30)
    max_retries: Mapped[int] = mapped_column(nullable=False, default=0)
    circuit_breaker_threshold: Mapped[int] = mapped_column(nullable=False, default=5)
    circuit_breaker_recovery: Mapped[int] = mapped_column(nullable=False, default=300)
    access_role: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    health_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    consecutive_failures: Mapped[int] = mapped_column(nullable=False, default=0)
    circuit_open_until: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_test_result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_test_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_test_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    creator = relationship("User", lazy="selectin")
    tools = relationship("McpTool", back_populates="mcp", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_mcp_enabled", "is_enabled"),
        Index("idx_mcp_creator", "creator_id"),
    )


class McpTool(Base):
    __tablename__ = "mcp_tools"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mcp_id: Mapped[int] = mapped_column(
        ForeignKey("mcps.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    mcp = relationship("Mcp", back_populates="tools")

    __table_args__ = (
        Index("idx_mcp_tool_enabled", "mcp_id", "is_enabled"),
        Index("uk_mcp_tool_name", "mcp_id", "tool_name", unique=True),
    )
