"""
Skill 激活管理器
消息事件驱动 + 会话投影缓存
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message_skill_event import MessageSkillEvent
from app.models.skill import Skill, SkillVersion
from app.services.sandbox_file_manager import SandboxFileManager

logger = logging.getLogger(__name__)


class SkillActivationManager:
    """Skill 激活管理器（消息层事件为唯一事实来源）。"""

    MAX_ACTIVE_SKILLS = 3

    SOURCE_LLM_MCP = "llm_mcp"
    SOURCE_MARKETPLACE = "marketplace"
    SOURCE_SLASH_COMMAND = "slash_command"
    SOURCE_MANUAL_API = "manual_api"
    SOURCE_MANUAL_BIND = "manual_bind"
    SOURCE_LEGACY = "legacy_projection"
    SOURCE_SYSTEM = "system"
    SOURCE_SYSTEM_REPLACE = "system_replace"

    MANUAL_PREFERRED_SOURCES = {
        SOURCE_MARKETPLACE,
        SOURCE_SLASH_COMMAND,
        SOURCE_MANUAL_API,
        SOURCE_MANUAL_BIND,
    }

    @staticmethod
    def enforce_skill_limit(active_ids: list[int]) -> list[int]:
        """
        兼容旧逻辑：对纯 skill_id 列表按时间顺序裁剪到上限。
        """
        removed_ids: list[int] = []
        while len(active_ids) >= SkillActivationManager.MAX_ACTIVE_SKILLS:
            removed_ids.append(active_ids.pop(0))
        return removed_ids

    @staticmethod
    def _get_published_version(skill: Skill, db: Session) -> Optional[SkillVersion]:
        if not skill.published_version_id:
            return None
        return (
            db.query(SkillVersion)
            .filter(SkillVersion.id == skill.published_version_id)
            .first()
        )

    @staticmethod
    def _resolve_manual_preferred(
        source: str, explicit_value: Optional[bool]
    ) -> bool:
        if explicit_value is not None:
            return bool(explicit_value)
        return source in SkillActivationManager.MANUAL_PREFERRED_SOURCES

    @staticmethod
    def _pick_eviction_index(active_projection: list[dict]) -> int:
        """
        软偏好淘汰策略：
        1. 优先淘汰非手工偏好技能
        2. 同优先级下淘汰最早激活（列表前部）
        """
        if not active_projection:
            return 0

        candidate_priority = min(
            1 if item.get("is_manual_preferred") else 0 for item in active_projection
        )
        for idx, item in enumerate(active_projection):
            if (1 if item.get("is_manual_preferred") else 0) == candidate_priority:
                return idx
        return 0

    @staticmethod
    def _normalize_projection_with_limit(items: list[dict]) -> tuple[list[dict], list[int]]:
        removed_ids: list[int] = []
        while len(items) > SkillActivationManager.MAX_ACTIVE_SKILLS:
            remove_index = SkillActivationManager._pick_eviction_index(items)
            removed = items.pop(remove_index)
            removed_ids.append(removed["id"])
        return items, removed_ids

    @staticmethod
    def _build_projection_from_events(events: list[MessageSkillEvent]) -> list[dict]:
        active: list[dict] = []

        for event in events:
            skill_id = int(event.skill_id)
            if event.event_type == "activate":
                active = [item for item in active if item["id"] != skill_id]
                active.append(
                    {
                        "id": skill_id,
                        "source": event.source,
                        "is_manual_preferred": bool(event.is_manual_preferred),
                        "activated_at": event.created_at.isoformat()
                        if event.created_at
                        else None,
                    }
                )
                active, _ = SkillActivationManager._normalize_projection_with_limit(active)
            elif event.event_type in {"deactivate", "remove"}:
                active = [item for item in active if item["id"] != skill_id]

        return active

    @staticmethod
    def _ensure_primary_skill_in_projection(
        conv: Conversation, projection: list[dict], has_events: bool
    ) -> list[dict]:
        if has_events:
            return projection
        if not conv.skill_id:
            return projection
        if any(item["id"] == conv.skill_id for item in projection):
            return projection
        projection.append(
            {
                "id": int(conv.skill_id),
                "source": SkillActivationManager.SOURCE_MANUAL_BIND,
                "is_manual_preferred": True,
                "activated_at": None,
            }
        )
        projection, _ = SkillActivationManager._normalize_projection_with_limit(projection)
        return projection

    @staticmethod
    def rebuild_projection_for_conversation(
        conv: Conversation, db: Session
    ) -> list[dict]:
        events = (
            db.query(MessageSkillEvent)
            .filter(MessageSkillEvent.conversation_id == conv.id)
            .order_by(MessageSkillEvent.created_at.asc(), MessageSkillEvent.id.asc())
            .all()
        )
        projection = SkillActivationManager._build_projection_from_events(events)
        projection = SkillActivationManager._ensure_primary_skill_in_projection(
            conv, projection, has_events=bool(events)
        )
        conv.set_active_skill_projection(projection)
        return projection

    @staticmethod
    def log_skill_event(
        *,
        conversation_id: int,
        skill_id: int,
        event_type: str,
        source: str,
        db: Session,
        message_id: Optional[int] = None,
        manual_preferred: Optional[bool] = None,
    ) -> MessageSkillEvent:
        event = MessageSkillEvent(
            conversation_id=conversation_id,
            message_id=message_id,
            skill_id=skill_id,
            event_type=event_type,
            source=source,
            is_manual_preferred=SkillActivationManager._resolve_manual_preferred(
                source, manual_preferred
            ),
        )
        db.add(event)
        db.flush()
        return event

    @staticmethod
    def activate_skill(
        skill_id: int,
        conversation_id: int,
        db: Session,
        user_id: int,
        *,
        source: str = SOURCE_MANUAL_API,
        message_id: Optional[int] = None,
        manual_preferred: Optional[bool] = None,
    ) -> dict:
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if not skill:
            return {
                "success": False,
                "message": f"Skill (id={skill_id}) 不存在",
                "skill_name": None,
                "prompt": None,
            }

        if skill.status != "published":
            return {
                "success": False,
                "message": f"Skill「{skill.name}」未发布",
                "skill_name": skill.name,
                "prompt": None,
            }

        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if not conv:
            return {
                "success": False,
                "message": "对话不存在",
                "skill_name": skill.name,
                "prompt": None,
            }

        before_projection = SkillActivationManager.rebuild_projection_for_conversation(
            conv, db
        )
        before_ids = [item["id"] for item in before_projection]
        if skill_id in before_ids:
            return {
                "success": False,
                "message": f"Skill「{skill.name}」已激活",
                "skill_name": skill.name,
                "prompt": None,
            }

        version = SkillActivationManager._get_published_version(skill, db)
        if not version:
            return {
                "success": False,
                "message": f"Skill「{skill.name}」没有已发布的版本",
                "skill_name": skill.name,
                "prompt": None,
            }

        sandbox_manager = SandboxFileManager()
        sandbox_result = sandbox_manager.copy_skill_directory(
            conversation_id=conversation_id,
            skill_id=skill_id,
            package_path=version.package_path,
            skill_name=skill.name,
        )
        if not sandbox_result["success"]:
            logger.warning(
                "Skill 激活时复制技能目录失败: conversation_id=%s, skill_id=%s, message=%s",
                conversation_id,
                skill_id,
                sandbox_result["message"],
            )
        else:
            sandbox_manager.sync_sandbox_to_db(conversation_id, user_id, db)

        SkillActivationManager.log_skill_event(
            conversation_id=conversation_id,
            skill_id=skill_id,
            event_type="activate",
            source=source,
            db=db,
            message_id=message_id,
            manual_preferred=manual_preferred,
        )

        after_projection = SkillActivationManager.rebuild_projection_for_conversation(
            conv, db
        )
        after_ids = [item["id"] for item in after_projection]
        removed_skill_ids = [sid for sid in before_ids if sid not in after_ids]
        db.commit()

        removed_skill_names: list[str] = []
        if removed_skill_ids:
            removed_rows = (
                db.query(Skill.id, Skill.name).filter(Skill.id.in_(removed_skill_ids)).all()
            )
            removed_name_map = {row.id: row.name for row in removed_rows}
            removed_skill_names = [
                removed_name_map.get(removed_id, f"Skill (id={removed_id})")
                for removed_id in removed_skill_ids
            ]

        message = f"已成功激活「{skill.name}」技能。"
        if removed_skill_names:
            if len(removed_skill_names) == 1:
                message += f" 已自动停用「{removed_skill_names[0]}」以满足 3 个技能上限。"
            else:
                message += (
                    " 已自动停用技能："
                    + "、".join(f"「{name}」" for name in removed_skill_names)
                    + "。"
                )

        return {
            "success": True,
            "message": message,
            "skill_name": skill.name,
            "prompt": SkillActivationManager._format_skill_prompt(skill, version),
            "replaced_skill_ids": removed_skill_ids,
            "replaced_skill_names": removed_skill_names,
        }

    @staticmethod
    def deactivate_skill(
        skill_id: int,
        conversation_id: int,
        db: Session,
        user_id: int,
        *,
        source: str = SOURCE_MANUAL_API,
        message_id: Optional[int] = None,
    ) -> dict:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if not conv:
            return {"success": False, "message": "对话不存在"}

        projection = SkillActivationManager.rebuild_projection_for_conversation(conv, db)
        active_ids = [item["id"] for item in projection]
        if skill_id not in active_ids:
            return {"success": False, "message": f"Skill (id={skill_id}) 未激活"}

        SkillActivationManager.log_skill_event(
            conversation_id=conversation_id,
            skill_id=skill_id,
            event_type="deactivate",
            source=source,
            db=db,
            message_id=message_id,
            manual_preferred=False,
        )
        SkillActivationManager.rebuild_projection_for_conversation(conv, db)
        db.commit()
        return {"success": True, "message": f"Skill (id={skill_id}) 已停用"}

    @staticmethod
    def get_available_skills(db: Session) -> list[Skill]:
        return db.query(Skill).filter(Skill.status == "published").all()

    @staticmethod
    def generate_activation_tools(db: Session) -> list[dict]:
        skills = SkillActivationManager.get_available_skills(db)
        tools: list[dict] = []
        for skill in skills:
            skill_version = SkillActivationManager._get_published_version(skill, db)
            description = skill_version.brief_desc if skill_version else ""
            if not description:
                description = f"{skill.name} 技能"
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"activate_skill_{skill.id}",
                        "description": f"激活「{skill.name}」：{description}",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    },
                }
            )
        return tools

    @staticmethod
    def parse_activation_tool_call(tool_name: str) -> Optional[int]:
        if tool_name.startswith("activate_skill_"):
            try:
                return int(tool_name.split("_")[-1])
            except (ValueError, IndexError):
                return None
        return None

    @staticmethod
    def _resolve_projection_with_fallback(
        conv: Conversation, db: Session
    ) -> list[dict]:
        projection = SkillActivationManager.rebuild_projection_for_conversation(conv, db)
        if projection:
            return projection
        if conv.skill_id:
            return [
                {
                    "id": int(conv.skill_id),
                    "source": SkillActivationManager.SOURCE_MANUAL_BIND,
                    "is_manual_preferred": True,
                    "activated_at": None,
                }
            ]
        return []

    @staticmethod
    def get_active_skills(conversation_id: int, db: Session, user_id: int) -> list[dict]:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if not conv:
            return []

        projection = SkillActivationManager._resolve_projection_with_fallback(conv, db)
        if not projection:
            return []

        active_ids = [item["id"] for item in projection]
        skills = db.query(Skill).filter(Skill.id.in_(active_ids)).all()
        published_version_ids = [
            s.published_version_id for s in skills if s.published_version_id
        ]
        skill_versions = (
            db.query(SkillVersion)
            .filter(SkillVersion.id.in_(published_version_ids))
            .all()
            if published_version_ids
            else []
        )
        version_map = {sv.skill_id: sv for sv in skill_versions}
        skill_map = {s.id: s for s in skills}

        result: list[dict] = []
        for item in projection:
            skill_id = item["id"]
            skill = skill_map.get(skill_id)
            if not skill:
                continue
            brief_desc = ""
            if skill_id in version_map:
                brief_desc = version_map[skill_id].brief_desc or skill.description
            result.append(
                {
                    "id": skill.id,
                    "name": skill.name,
                    "brief_desc": brief_desc,
                    "source": item.get("source"),
                    "is_manual_preferred": bool(item.get("is_manual_preferred")),
                    "activated_at": item.get("activated_at"),
                }
            )
        return result

    @staticmethod
    def get_active_skills_with_order(
        conversation_id: int, db: Session, user_id: int
    ) -> list[dict]:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if not conv:
            return []

        projection = SkillActivationManager._resolve_projection_with_fallback(conv, db)
        if not projection:
            return []

        active_ids = [item["id"] for item in projection]
        skills = db.query(Skill).filter(Skill.id.in_(active_ids)).all()
        published_version_ids = [
            s.published_version_id for s in skills if s.published_version_id
        ]
        skill_versions = (
            db.query(SkillVersion)
            .filter(SkillVersion.id.in_(published_version_ids))
            .all()
            if published_version_ids
            else []
        )
        version_map = {sv.skill_id: sv for sv in skill_versions}
        skill_map = {s.id: s for s in skills}

        result: list[dict] = []
        for item in projection:
            skill_id = item["id"]
            skill = skill_map.get(skill_id)
            version = version_map.get(skill_id)
            if not skill or not version:
                continue
            result.append(
                {
                    "id": skill.id,
                    "name": skill.name,
                    "brief_desc": version.brief_desc or skill.description,
                    "system_prompt": version.system_prompt,
                    "bound_mcps": version.bound_mcps,
                }
            )
        return result

    @staticmethod
    def combine_multiple_prompts(skills: list[dict]) -> str:
        if not skills:
            return ""
        parts = []
        for skill in skills:
            part = f"""
=== Skill 上下文 ===
技能名称：{skill["name"]}
技能说明：{skill["brief_desc"]}

执行要求：
{skill["system_prompt"]}
""".strip()
            parts.append(part)
        return "\n\n".join(parts)

    @staticmethod
    def get_combined_tools_for_skills(skills: list[dict], db: Session) -> list[dict]:
        from app.models.mcp import Mcp

        all_mcp_ids = set()
        for skill in skills:
            bound_mcps = skill.get("bound_mcps", [])
            if not bound_mcps:
                continue
            for mcp in bound_mcps:
                if hasattr(mcp, "id"):
                    all_mcp_ids.add(mcp.id)
                elif isinstance(mcp, dict) and "id" in mcp:
                    all_mcp_ids.add(mcp["id"])
                elif isinstance(mcp, int):
                    all_mcp_ids.add(mcp)

        if not all_mcp_ids:
            return []

        mcps = (
            db.query(Mcp)
            .filter(
                Mcp.id.in_(list(all_mcp_ids)),
                Mcp.is_enabled == True,
                Mcp.health_status != "circuit_open",
            )
            .all()
        )

        tools: list[dict] = []
        seen_tool_names = set()
        for mcp in mcps:
            enabled_tools = [t for t in (mcp.tools or []) if t.is_enabled]
            for tool in enabled_tools:
                tool_key = f"{mcp.id}__{tool.tool_name}"
                if tool_key in seen_tool_names:
                    continue
                seen_tool_names.add(tool_key)
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool_key,
                            "description": tool.tool_description or "",
                            "parameters": tool.input_schema
                            or {"type": "object", "properties": {}},
                        },
                    }
                )
        return tools

    @staticmethod
    def ensure_conversation_primary_skill_event(
        conversation_id: int,
        skill_id: int,
        db: Session,
        *,
        source: str = SOURCE_MANUAL_BIND,
        manual_preferred: Optional[bool] = True,
    ) -> None:
        existing = (
            db.query(MessageSkillEvent.id)
            .filter(
                MessageSkillEvent.conversation_id == conversation_id,
                MessageSkillEvent.skill_id == skill_id,
                MessageSkillEvent.event_type == "activate",
            )
            .first()
        )
        if not existing:
            SkillActivationManager.log_skill_event(
                conversation_id=conversation_id,
                skill_id=skill_id,
                event_type="activate",
                source=source,
                db=db,
                message_id=None,
                manual_preferred=manual_preferred,
            )

        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv:
            SkillActivationManager.rebuild_projection_for_conversation(conv, db)

    @staticmethod
    def _format_skill_prompt(skill: Skill, version: SkillVersion) -> str:
        return f"""
=== Skill 上下文 ===
技能名称：{skill.name}
技能说明：{version.brief_desc or skill.description}

执行要求：
{version.system_prompt}
""".strip()
