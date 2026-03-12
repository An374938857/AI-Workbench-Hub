from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Index
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class McpCallLog(Base):
    __tablename__ = "mcp_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    mcp_id: Mapped[int] = mapped_column(ForeignKey("mcps.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[str]] = mapped_column(Text().with_variant(MEDIUMTEXT, "mysql"), nullable=True)
    is_success: Mapped[bool] = mapped_column(nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_mcplog_user_time", "user_id", "created_at"),
        Index("idx_mcplog_mcp_time", "mcp_id", "created_at"),
        Index("idx_mcplog_conversation", "conversation_id"),
        Index("idx_mcplog_tool_time", "tool_name", "created_at"),
    )
