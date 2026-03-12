from datetime import datetime

from sqlalchemy import ForeignKey, String, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSortPreference(Base):
    __tablename__ = "user_sort_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int] = mapped_column(nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uk_user_type_target"),
        Index("idx_user_type_sort", "user_id", "target_type", "sort_order"),
    )
