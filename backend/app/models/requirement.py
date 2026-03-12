from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="P2")
    workflow_definition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workflow_definitions.id"), nullable=True
    )
    workflow_instance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workflow_instances.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NOT_STARTED")
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    project = relationship("Project", lazy="selectin")
    workflow_definition = relationship("WorkflowDefinition", lazy="selectin")
    workflow_instance = relationship("WorkflowInstance", lazy="selectin")

    __table_args__ = (
        Index("idx_requirement_project", "project_id"),
        Index("idx_requirement_status", "status"),
        Index("idx_requirement_priority", "priority"),
    )
