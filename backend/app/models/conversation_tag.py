from datetime import datetime

from sqlalchemy import ForeignKey, String, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConversationTag(Base):
    __tablename__ = "conversation_tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#409eff")
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    relations = relationship(
        "ConversationTagRelation",
        back_populates="tag",
        cascade="all, delete-orphan",
        lazy="noload",
        overlaps="tags",
    )

    __table_args__ = (
        Index("idx_tag_user_sort", "user_id", "sort_order"),
        UniqueConstraint("user_id", "name", name="uk_user_tag_name"),
    )


class ConversationTagRelation(Base):
    __tablename__ = "conversation_tag_relations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("conversation_tags.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)

    tag = relationship(
        "ConversationTag",
        back_populates="relations",
        lazy="selectin",
        overlaps="tags",
    )

    __table_args__ = (
        UniqueConstraint("conversation_id", "tag_id", name="uk_conv_tag"),
        Index("idx_tagrel_tag", "tag_id"),
    )
