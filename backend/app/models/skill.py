from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Index, Column, Table, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

skill_tags = Table(
    "skill_tags",
    Base.metadata,
    Column(
        "skill_id",
        Integer,
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("scene_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    icon_emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    published_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("skill_versions.id", use_alter=True), nullable=True
    )
    draft_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("skill_versions.id", use_alter=True), nullable=True
    )
    sort_weight: Mapped[int] = mapped_column(nullable=False, default=0)
    use_count: Mapped[int] = mapped_column(nullable=False, default=0)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    tags = relationship("SceneTag", secondary=skill_tags, lazy="selectin")
    creator = relationship("User", lazy="selectin")
    published_version = relationship(
        "SkillVersion",
        foreign_keys=[published_version_id],
        lazy="selectin",
        post_update=True,
    )
    draft_version = relationship(
        "SkillVersion",
        foreign_keys=[draft_version_id],
        lazy="selectin",
        post_update=True,
    )

    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_creator", "creator_id"),
    )


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    brief_desc: Mapped[str] = mapped_column(String(1000), nullable=False)
    detail_desc: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    welcome_message: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider_id: Mapped[int] = mapped_column(
        ForeignKey("model_providers.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    package_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    change_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mcp_load_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="all", server_default="all"
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    bound_mcps = relationship("Mcp", secondary="skill_mcps", lazy="selectin")

    __table_args__ = (Index("idx_skill_version", "skill_id", "version_number"),)
