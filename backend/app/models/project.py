from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

project_owners = Table(
    "project_owners",
    Base.metadata,
    Column(
        "project_id",
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    metis_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    workflow_definition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workflow_definitions.id"), nullable=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    owners = relationship("User", secondary=project_owners, lazy="selectin")
    workflow_definition = relationship("WorkflowDefinition", lazy="selectin")

    __table_args__ = (
        Index("idx_project_level", "level"),
        Index("idx_project_workflow_definition", "workflow_definition_id"),
    )
