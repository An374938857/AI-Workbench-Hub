from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Index
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text().with_variant(MEDIUMTEXT, "mysql"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")  # upload | generated
    # 新增字段
    sandbox_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 沙箱内相对路径
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    __table_args__ = (Index("idx_conversation", "conversation_id"),)
