from datetime import datetime
from sqlalchemy import TEXT, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ConversationCompressionLog(Base):
    __tablename__ = "conversation_compression_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    original_token_count: Mapped[int] = mapped_column()
    compressed_token_count: Mapped[int] = mapped_column()
    summary: Mapped[str] = mapped_column(TEXT)
    split_message_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    __table_args__ = (
        Index("idx_conv_created", "conversation_id", "created_at"),
    )
