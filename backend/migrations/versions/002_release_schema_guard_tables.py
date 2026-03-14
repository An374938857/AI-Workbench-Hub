"""ensure release critical tables exist

Revision ID: 002
Revises: 001
Create Date: 2026-03-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND index_name = :index_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    ).fetchone()
    return result is not None


def _ensure_index(
    table_name: str,
    index_name: str,
    columns: list[str],
    unique: bool = False,
) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _table_exists("conversation_compression_logs"):
        op.create_table(
            "conversation_compression_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("conversation_id", sa.Integer(), nullable=False),
            sa.Column("original_token_count", sa.Integer(), nullable=False),
            sa.Column("compressed_token_count", sa.Integer(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("split_message_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index(
        "conversation_compression_logs",
        "idx_conv_created",
        ["conversation_id", "created_at"],
    )

    if not _table_exists("custom_commands"):
        op.create_table(
            "custom_commands",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=50), nullable=False),
            sa.Column("description", sa.String(length=200), nullable=False),
            sa.Column("action_type", sa.String(length=50), nullable=False),
            sa.Column("action_params", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("custom_commands", "idx_user_name", ["user_id", "name"], unique=True)

    if not _table_exists("model_fallback_configs"):
        op.create_table(
            "model_fallback_configs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_provider_id", sa.Integer(), nullable=True),
            sa.Column("source_model_name", sa.String(length=100), nullable=True),
            sa.Column("fallback_chain", sa.JSON(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["source_provider_id"],
                ["model_providers.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index(
        "model_fallback_configs",
        "idx_fallback_source",
        ["source_provider_id", "source_model_name"],
    )

    if not _table_exists("model_fallback_logs"):
        op.create_table(
            "model_fallback_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("conversation_id", sa.Integer(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=True),
            sa.Column("original_provider_id", sa.Integer(), nullable=False),
            sa.Column("original_model_name", sa.String(length=100), nullable=False),
            sa.Column("fallback_provider_id", sa.Integer(), nullable=False),
            sa.Column("fallback_model_name", sa.String(length=100), nullable=False),
            sa.Column("error_type", sa.String(length=50), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index(
        "model_fallback_logs",
        "idx_fallback_log_conv",
        ["conversation_id", "created_at"],
    )
    _ensure_index(
        "model_fallback_logs",
        "idx_fallback_log_model",
        ["original_provider_id", "original_model_name"],
    )

    if not _table_exists("model_comparisons"):
        op.create_table(
            "model_comparisons",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("conversation_id", sa.Integer(), nullable=False),
            sa.Column("user_message_id", sa.Integer(), nullable=False),
            sa.Column("model_a_provider_id", sa.Integer(), nullable=False),
            sa.Column("model_a_name", sa.String(length=100), nullable=False),
            sa.Column("model_a_message_id", sa.Integer(), nullable=True),
            sa.Column("model_b_provider_id", sa.Integer(), nullable=False),
            sa.Column("model_b_name", sa.String(length=100), nullable=False),
            sa.Column("model_b_message_id", sa.Integer(), nullable=True),
            sa.Column("winner", sa.String(length=10), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_message_id"], ["messages.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["model_a_message_id"], ["messages.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["model_b_message_id"], ["messages.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index(
        "model_comparisons",
        "idx_comparison_conv",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS model_comparisons"))
    op.execute(sa.text("DROP TABLE IF EXISTS model_fallback_logs"))
    op.execute(sa.text("DROP TABLE IF EXISTS model_fallback_configs"))
    op.execute(sa.text("DROP TABLE IF EXISTS custom_commands"))
    op.execute(sa.text("DROP TABLE IF EXISTS conversation_compression_logs"))
