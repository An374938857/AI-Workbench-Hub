from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Text

from app.database import Base


class ConversationReferenceState(Base):
    __tablename__ = "conversation_reference_state"

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    scope_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reference_scope_snapshot.id", ondelete="SET NULL"), nullable=True
    )
    selected_file_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    empty_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    selection_version: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )
    cleared_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("idx_reference_state_updated", "updated_at"),)


class ReferenceScopeSnapshot(Base):
    __tablename__ = "reference_scope_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    binding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    binding_id: Mapped[int] = mapped_column(nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_ref_scope_conv_created", "conversation_id", "created_at"),
    )


class FileLightIndex(Base):
    __tablename__ = "file_light_index"

    file_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    summary: Mapped[Optional[str]] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    keywords_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    outline_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    embedding_type: Mapped[str] = mapped_column(String(16), primary_key=True, nullable=False, default="TEXT")
    embedding_model_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    embedding_dim: Mapped[Optional[int]] = mapped_column(nullable=True)
    vector_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    index_version: Mapped[int] = mapped_column(nullable=False, default=1)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    index_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    last_error: Mapped[Optional[str]] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)

    __table_args__ = (
        Index("idx_file_light_tenant_type", "tenant_id", "embedding_type"),
        Index("idx_file_light_model_version", "embedding_model_id", "index_version"),
        Index("idx_file_light_status_indexed", "index_status", "indexed_at"),
    )


class ReferenceAuditLog(Base):
    __tablename__ = "reference_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    query_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=False)
    recommended_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    final_selected_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    injected_chunks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    token_usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tenant_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_ref_audit_conv_created", "conversation_id", "created_at"),
        Index("idx_ref_audit_tenant_created", "tenant_id", "created_at"),
    )


class EmbeddingRebuildTask(Base):
    __tablename__ = "embedding_rebuild_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    embedding_type: Mapped[str] = mapped_column(String(16), nullable=False)  # TEXT/MULTIMODAL
    target_model_id: Mapped[int] = mapped_column(ForeignKey("model_list.id"), nullable=False)
    trigger_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")  # PENDING/RUNNING/SUCCEEDED/FAILED
    cursor_file_id: Mapped[int] = mapped_column(nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    discovered_count: Mapped[int] = mapped_column(nullable=False, default=0)
    succeeded_count: Mapped[int] = mapped_column(nullable=False, default=0)
    retryable_failed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    current_batch_no: Mapped[int] = mapped_column(nullable=False, default=0)
    total_batches: Mapped[int] = mapped_column(nullable=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column(nullable=False, default=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now, onupdate=datetime.now)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_embedding_task_status_updated", "status", "updated_at"),
        Index("idx_embedding_task_type_model", "embedding_type", "target_model_id"),
    )


class EmbeddingRebuildTaskItem(Base):
    __tablename__ = "embedding_rebuild_task_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("embedding_rebuild_tasks.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    route_type: Mapped[str] = mapped_column(String(16), nullable=False, default="TEXT")
    content_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now, onupdate=datetime.now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_embedding_task_item_task_status", "task_id", "status"),
        Index("idx_embedding_task_item_task_file", "task_id", "file_id"),
    )
