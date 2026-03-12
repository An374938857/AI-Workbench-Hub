"""
Skill 渐进式披露服务
实现三层加载逻辑
- Level 1: 对话初始化时加载 Skill 元信息（name + brief_desc）
- Level 2: Skill 激活时加载 system_prompt
- Level 3: 按需读取 Skill 目录下的 skills/（兼容 references/）
"""

import logging
import os
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.models.skill import Skill, SkillVersion
from app.services.skill_activation_manager import SkillActivationManager

logger = logging.getLogger(__name__)


class SkillProgressiveDisclosure:
    """Skill 渐进式披露管理器"""

    # Skill 目录基础路径
    SKILLS_BASE_DIR = "/data/skills"
    SKILL_FILES_SUBDIR = "skills"
    LEGACY_SKILL_FILES_SUBDIR = "references"

    @staticmethod
    def get_skill_metadata(skill_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Level 1: 获取 Skill 元信息（最小化信息）

        Args:
            skill_id: Skill ID
            db: 数据库会话

        Returns:
            包含 name 和 brief_desc 的元信息
        """
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if not skill:
            return None

        # 获取最新发布版本
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.version_number.desc())
            .first()
        )

        if not version:
            return None

        return {
            "id": skill.id,
            "name": skill.name,
            "brief_desc": version.brief_desc,
            "icon_emoji": skill.icon_emoji,
        }

    @staticmethod
    def get_skill_system_prompt(skill_id: int, db: Session) -> Optional[str]:
        """
        Level 2: 获取 Skill 的 system_prompt

        Args:
            skill_id: Skill ID
            db: 数据库会话

        Returns:
            system_prompt 内容
        """
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.version_number.desc())
            .first()
        )

        if not version:
            return None

        return version.system_prompt

    @staticmethod
    def read_skill_reference(
        skill_id: int, reference_path: str, db: Session
    ) -> Dict[str, Any]:
        """
        Level 3: 读取 Skill 目录下的参考文档

        Args:
            skill_id: Skill ID
            reference_path: 参考文档路径（如 "api-guide.md"）
            db: 数据库会话

        Returns:
            {
                "success": bool,
                "content": str,
                "message": str
            }
        """
        # 安全检查：防止路径遍历
        if ".." in reference_path or reference_path.startswith("/"):
            return {"success": False, "content": "", "message": "非法路径"}

        # 构建完整路径
        full_path = os.path.join(
            SkillProgressiveDisclosure.SKILLS_BASE_DIR,
            str(skill_id),
            SkillProgressiveDisclosure.SKILL_FILES_SUBDIR,
            reference_path,
        )
        if not os.path.exists(full_path):
            full_path = os.path.join(
                SkillProgressiveDisclosure.SKILLS_BASE_DIR,
                str(skill_id),
                SkillProgressiveDisclosure.LEGACY_SKILL_FILES_SUBDIR,
                reference_path,
            )

        # 检查文件是否存在
        if not os.path.exists(full_path):
            return {
                "success": False,
                "content": "",
                "message": f"参考文档不存在: {reference_path}",
            }

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            return {"success": True, "content": content, "message": "读取成功"}
        except Exception as e:
            logger.error(f"读取 Skill 参考文档失败: {full_path}, {e}")
            return {"success": False, "content": "", "message": f"读取失败: {str(e)}"}

    @staticmethod
    def list_skill_references(skill_id: int) -> Dict[str, Any]:
        """
        列出 Skill 目录下的所有参考文档

        Args:
            skill_id: Skill ID

        Returns:
            {
                "success": bool,
                "files": List[str],
                "message": str
            }
        """
        references_dir = os.path.join(
            SkillProgressiveDisclosure.SKILLS_BASE_DIR,
            str(skill_id),
            SkillProgressiveDisclosure.SKILL_FILES_SUBDIR,
        )
        if not os.path.exists(references_dir):
            references_dir = os.path.join(
                SkillProgressiveDisclosure.SKILLS_BASE_DIR,
                str(skill_id),
                SkillProgressiveDisclosure.LEGACY_SKILL_FILES_SUBDIR,
            )

        if not os.path.exists(references_dir):
            return {"success": True, "files": [], "message": "无参考文档"}

        try:
            files = []
            for item in os.listdir(references_dir):
                item_path = os.path.join(references_dir, item)
                if os.path.isfile(item_path):
                    files.append(item)

            return {
                "success": True,
                "files": files,
                "message": f"找到 {len(files)} 个参考文档",
            }
        except Exception as e:
            logger.error(f"列出 Skill 参考文档失败: {references_dir}, {e}")
            return {"success": False, "files": [], "message": f"列出失败: {str(e)}"}

    @staticmethod
    def build_context_with_progressive_disclosure(
        conversation_id: int, db: Session, user_id: int
    ) -> Dict[str, Any]:
        """
        构建包含渐进式披露的上下文

        Args:
            conversation_id: 对话 ID
            db: 数据库会话
            user_id: 用户 ID

        Returns:
            {
                "skill_metadatas": List[Dict],  # Level 1: 所有激活 Skill 的元信息
                "active_prompts": List[str],    # Level 2: 已激活 Skill 的 prompts
                "references_available": List[str]  # Level 3: 可读取的参考文档列表
            }
        """
        # 获取激活的 Skill 列表
        active_skills = SkillActivationManager.get_active_skills_with_order(
            conversation_id, db, user_id
        )

        result = {
            "skill_metadatas": [],
            "active_prompts": [],
            "references_available": [],
        }

        for skill in active_skills:
            # Level 1: 元信息
            metadata = SkillProgressiveDisclosure.get_skill_metadata(skill["id"], db)
            if metadata:
                result["skill_metadatas"].append(metadata)

            # Level 2: System prompt
            prompt = SkillProgressiveDisclosure.get_skill_system_prompt(skill["id"], db)
            if prompt:
                result["active_prompts"].append(
                    {
                        "skill_id": skill["id"],
                        "skill_name": skill["name"],
                        "prompt": prompt,
                    }
                )

            # Level 3: 检查可用的参考文档
            refs = SkillProgressiveDisclosure.list_skill_references(skill["id"])
            if refs["success"] and refs["files"]:
                result["references_available"].extend(
                    [f"{skill['name']}/{f}" for f in refs["files"]]
                )

        return result
