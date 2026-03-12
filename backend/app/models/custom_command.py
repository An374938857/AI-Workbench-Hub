from datetime import datetime
from typing import Optional
from sqlalchemy import String, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CustomCommand(Base):
    __tablename__ = "custom_commands"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(200))
    action_type: Mapped[str] = mapped_column(String(50))
    action_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    __table_args__ = (
        Index("idx_user_name", "user_id", "name", unique=True),
    )
