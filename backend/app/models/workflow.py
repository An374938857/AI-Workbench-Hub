from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # PROJECT/REQUIREMENT
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    versions = relationship(
        "WorkflowDefinitionVersion",
        back_populates="workflow_definition",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("scope", "code", name="uq_workflow_scope_code"),
        Index("idx_workflow_scope_status", "scope", "status"),
    )


class WorkflowDefinitionVersion(Base):
    __tablename__ = "workflow_definition_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(nullable=False)
    version_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    workflow_definition = relationship("WorkflowDefinition", back_populates="versions", lazy="selectin")
    nodes = relationship(
        "WorkflowDefinitionNode",
        back_populates="workflow_definition_version",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "workflow_definition_id",
            "version_no",
            name="uq_workflow_definition_version_no",
        ),
        Index("idx_workflow_version_published", "workflow_definition_id", "is_published"),
    )


class WorkflowDefinitionNode(Base):
    __tablename__ = "workflow_definition_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_definition_version_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definition_versions.id", ondelete="CASCADE"), nullable=False
    )
    node_code: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    node_order: Mapped[int] = mapped_column(nullable=False)
    skill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("skills.id"), nullable=True)
    input_mapping_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    retry_policy_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    workflow_definition_version = relationship(
        "WorkflowDefinitionVersion",
        back_populates="nodes",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "workflow_definition_version_id",
            "node_code",
            name="uq_workflow_version_node_code",
        ),
        UniqueConstraint(
            "workflow_definition_version_id",
            "node_order",
            name="uq_workflow_version_node_order",
        ),
    )


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)  # PROJECT/REQUIREMENT
    scope_id: Mapped[int] = mapped_column(nullable=False)
    workflow_definition_id: Mapped[int] = mapped_column(ForeignKey("workflow_definitions.id"), nullable=False)
    workflow_definition_version_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definition_versions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NOT_STARTED")
    current_node_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workflow_instance_nodes.id"), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    nodes = relationship(
        "WorkflowInstanceNode",
        back_populates="workflow_instance",
        cascade="all, delete-orphan",
        foreign_keys="WorkflowInstanceNode.workflow_instance_id",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_workflow_instance_scope", "scope_type", "scope_id"),
        Index("idx_workflow_instance_status_updated", "status", "updated_at"),
    )


class WorkflowInstanceNode(Base):
    __tablename__ = "workflow_instance_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False
    )
    definition_node_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definition_nodes.id"), nullable=False
    )
    node_code: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    node_order: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    manual_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skip_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_affected: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )

    workflow_instance = relationship(
        "WorkflowInstance",
        back_populates="nodes",
        foreign_keys=[workflow_instance_id],
        lazy="selectin",
    )
    conversations = relationship(
        "WorkflowNodeConversation",
        back_populates="workflow_instance_node",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("workflow_instance_id", "node_code", name="uq_instance_node_code"),
        Index("idx_instance_node_order", "workflow_instance_id", "node_order"),
        Index("idx_instance_node_status", "workflow_instance_id", "status"),
    )


class WorkflowNodeConversation(Base):
    __tablename__ = "workflow_node_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_instance_node_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instance_nodes.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    binding_type: Mapped[str] = mapped_column(String(16), nullable=False, default="AUTO", server_default="AUTO")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    workflow_instance_node = relationship(
        "WorkflowInstanceNode",
        back_populates="conversations",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_workflow_conversation_single_node"),
    )


class WorkflowTransitionLog(Base):
    __tablename__ = "workflow_transition_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instances.id"), nullable=False)
    workflow_instance_node_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workflow_instance_nodes.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_overridden: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    operator_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_transition_instance_created_at", "workflow_instance_id", "created_at"),
        Index("idx_transition_operator_created_at", "operator_user_id", "created_at"),
    )


class WorkflowInstanceNodeOutput(Base):
    __tablename__ = "workflow_instance_node_outputs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_instance_node_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instance_nodes.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True
    )
    output_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    deliverable_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_ref: Mapped[str] = mapped_column(Text, nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index(
            "idx_node_output_deliverable_version",
            "workflow_instance_node_id",
            "deliverable_type",
            "version_no",
        ),
        Index("idx_node_output_kind_created", "workflow_instance_node_id", "output_kind", "created_at"),
        Index("idx_node_output_current", "workflow_instance_node_id", "is_current"),
    )
