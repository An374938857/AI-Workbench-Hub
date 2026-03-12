from datetime import datetime
from typing import Optional
import json

from sqlalchemy import Boolean, ForeignKey, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    skill_id: Mapped[Optional[int]] = mapped_column(ForeignKey("skills.id"), nullable=True)
    skill_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("skill_versions.id"), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    current_provider_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    current_model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_test: Mapped[bool] = mapped_column(nullable=False, default=False)
    # 新增字段
    prompt_template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("system_prompt_templates.id"), nullable=True)
    active_skill_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON 格式存储激活的 Skill ID 列表
    sandbox_cleaned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sandbox_unread_change_count: Mapped[int] = mapped_column(nullable=False, default=0)
    sidebar_signal_state: Mapped[str] = mapped_column(
        String(48), nullable=False, default="none"
    )
    sidebar_signal_updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    sidebar_signal_read_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    live_status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    live_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    live_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    live_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    live_stage_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    live_stage_meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    live_round_no: Mapped[Optional[int]] = mapped_column(nullable=True)
    live_started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    live_updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    skill = relationship("Skill", lazy="selectin")
    tags = relationship(
        "ConversationTag",
        secondary="conversation_tag_relations",
        lazy="selectin",
        overlaps="relations,tag",
    )

    __table_args__ = (
        Index("idx_conversation_user_time", "user_id", "updated_at"),
        Index("idx_conversation_skill", "skill_id"),
        Index("idx_conversation_last_activity", "last_activity_at"),
    )

    def get_active_skill_ids(self) -> list[int]:
        """获取激活的 Skill ID 列表（按投影顺序）。"""
        return [item["id"] for item in self.get_active_skill_projection()]

    def get_active_skill_projection(self) -> list[dict]:
        """
        获取激活技能投影（会话缓存层）。

        兼容三种存储形态：
        1. {"skills":[...], "skill_ids":[...]} 新结构
        2. {"skill_ids":[...]} 旧字典结构
        3. [1,2,3] 旧数组结构
        """
        if not self.active_skill_ids:
            return []

        try:
            payload = json.loads(self.active_skill_ids)
        except (json.JSONDecodeError, TypeError):
            return []

        result: list[dict] = []
        if isinstance(payload, dict) and isinstance(payload.get("skills"), list):
            for item in payload["skills"]:
                if not isinstance(item, dict):
                    continue
                skill_id = item.get("id")
                try:
                    parsed_id = int(skill_id)
                except (TypeError, ValueError):
                    continue
                if parsed_id <= 0:
                    continue
                result.append(
                    {
                        "id": parsed_id,
                        "source": str(item.get("source") or "unknown"),
                        "is_manual_preferred": bool(
                            item.get("is_manual_preferred", False)
                        ),
                        "activated_at": item.get("activated_at"),
                    }
                )

        if result:
            return result

        legacy_ids: list = []
        if isinstance(payload, dict):
            ids = payload.get("skill_ids")
            if isinstance(ids, list):
                legacy_ids = ids
        elif isinstance(payload, list):
            legacy_ids = payload

        for skill_id in legacy_ids:
            try:
                parsed_id = int(skill_id)
            except (TypeError, ValueError):
                continue
            if parsed_id <= 0:
                continue
            result.append(
                {
                    "id": parsed_id,
                    "source": "legacy_projection",
                    "is_manual_preferred": False,
                    "activated_at": None,
                }
            )
        return result

    def set_active_skill_projection(self, projection: list[dict]) -> None:
        """写入激活技能投影（用于会话层缓存）。"""
        normalized: list[dict] = []
        for item in projection:
            if not isinstance(item, dict):
                continue
            skill_id = item.get("id")
            try:
                parsed_id = int(skill_id)
            except (TypeError, ValueError):
                continue
            if parsed_id <= 0:
                continue
            normalized.append(
                {
                    "id": parsed_id,
                    "source": str(item.get("source") or "unknown"),
                    "is_manual_preferred": bool(
                        item.get("is_manual_preferred", False)
                    ),
                    "activated_at": item.get("activated_at"),
                }
            )
        self.active_skill_ids = json.dumps(
            {"skills": normalized, "skill_ids": [item["id"] for item in normalized]},
            ensure_ascii=False,
        )

    def set_active_skill_ids(self, skill_ids: list[int]) -> None:
        """设置激活的 Skill ID 列表（兼容旧调用）。"""
        projection = [
            {
                "id": skill_id,
                "source": "legacy_projection",
                "is_manual_preferred": False,
                "activated_at": None,
            }
            for skill_id in skill_ids
        ]
        self.set_active_skill_projection(projection)
