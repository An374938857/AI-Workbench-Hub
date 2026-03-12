"""
Prompt 组合服务
实现三层 prompt 动态组合：默认 prompt → 角色模板 → Skill prompt
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.skill import Skill, SkillVersion
from app.models.system_prompt_template import SystemPromptTemplate
from app.models.system_config import SystemConfig


class PromptCombiner:
    """Prompt 组合器"""

    # Token 限制
    MAX_PROMPT_TOKENS = 8000

    # 分隔符
    SECTION_SEPARATOR = "\n\n"
    DEFAULT_SEPARATOR = "=== 基础定位 ==="
    TEMPLATE_SEPARATOR = "=== 角色模板 ==="
    SKILL_SEPARATOR = "=== Skill 上下文 ==="

    @staticmethod
    def _build_skill_sandbox_note(mount_dirname: str) -> str:
        """生成技能资源挂载说明。"""
        return (
            "技能资源访问说明：\n"
            f"- 该技能完整目录已挂载到对话沙箱 `skills/{mount_dirname}/`\n"
            "- 技能包内部目录结构不固定，可能包含 `assets/`、`scripts/`、`archive/`、`hooks/` 或其他自定义子目录\n"
            "- 读取模板、示例、脚本或资产前，优先调用 `sandbox_list_files` 查看 `skills` 目录下的实际文件树\n"
            f"- 读取文件时，推荐使用 `subdir=\"skills\"` 并传入相对路径（不要重复写 `skills/` 前缀），例如 `{mount_dirname}/assets/config.yaml` 或 `{mount_dirname}/hooks/openclaw/HOOK.md`\n"
            f"- 若使用更具体的 `subdir`（如 `skills/{mount_dirname}`），则 `filename` 只写子路径（如 `assets/config.yaml`），不要再重复 `{mount_dirname}/`"
        )

    @staticmethod
    def get_default_prompt(db: Session) -> Optional[str]:
        """
        获取默认 system prompt

        Args:
            db: 数据库会话

        Returns:
            默认 prompt 内容，如果未启用则返回 None
        """
        # 检查是否启用默认 prompt
        enable_config = db.query(SystemConfig).filter(
            SystemConfig.key == "enable_default_prompt"
        ).first()

        if not enable_config or not enable_config.get_value():
            return None

        # 获取默认 prompt 内容
        default_config = db.query(SystemConfig).filter(
            SystemConfig.key == "default_system_prompt"
        ).first()

        if not default_config or not default_config.value:
            return None

        return default_config.get_value()

    @staticmethod
    def get_template_prompt(
        db: Session,
        template_id: Optional[int],
        user_id: Optional[int] = None
    ) -> Optional[str]:
        """
        获取角色模板 prompt

        Args:
            db: 数据库会话
            template_id: 模板 ID
            user_id: 用户 ID（用于获取个人模板）

        Returns:
            模板 prompt 内容
        """
        if not template_id:
            # 如果没有指定模板，尝试获取全局默认模板
            template = db.query(SystemPromptTemplate).filter(
                SystemPromptTemplate.is_global_default == True
            ).first()
        else:
            template = db.query(SystemPromptTemplate).filter(
                SystemPromptTemplate.id == template_id
            ).first()

        if not template:
            return None

        # 检查可见性
        if template.visibility == "personal" and template.created_by != user_id:
            return None

        return template.content

    @staticmethod
    def get_skill_prompt(db: Session, skill_version_id: Optional[int]) -> Optional[str]:
        """
        获取 Skill prompt

        Args:
            db: 数据库会话
            skill_version_id: Skill 版本 ID

        Returns:
            Skill prompt 内容
        """
        if not skill_version_id:
            return None

        skill_version = db.query(SkillVersion).filter(
            SkillVersion.id == skill_version_id
        ).first()

        if not skill_version or not skill_version.system_prompt:
            return None

        # 通过 skill_id 查询 Skill
        skill = db.query(Skill).filter(Skill.id == skill_version.skill_id).first()
        if not skill:
            return None

        # 使用 <skill_context> 标签包裹
        from app.services.sandbox_file_manager import SandboxFileManager

        mount_dirname = SandboxFileManager.resolve_skill_mount_dirname(
            skill_version.package_path,
            skill.name,
        )
        sandbox_note = PromptCombiner._build_skill_sandbox_note(mount_dirname)

        return f"""
=== Skill 上下文 ===
技能名称：{skill.name}
技能说明：{skill_version.brief_desc or skill.description}

执行要求：
{skill_version.system_prompt}

{sandbox_note}
""".strip()

    @staticmethod
    def combine_prompts(
        db: Session,
        conversation: Conversation,
        user_id: Optional[int] = None
    ) -> str:
        """
        组合三层 prompt

        Args:
            db: 数据库会话
            conversation: 对话对象
            user_id: 用户 ID

        Returns:
            组合后的 prompt
        """
        parts = []

        # 1. 默认 prompt
        default_prompt = PromptCombiner.get_default_prompt(db)
        if default_prompt:
            parts.append(f"{PromptCombiner.DEFAULT_SEPARATOR}\n{default_prompt}")

        # 2. 角色模板 prompt
        template_prompt = PromptCombiner.get_template_prompt(
            db, conversation.prompt_template_id, user_id
        )
        if template_prompt:
            parts.append(f"{PromptCombiner.TEMPLATE_SEPARATOR}\n{template_prompt}")

        # 3. Skill prompt（主 Skill）
        if conversation.skill_version_id:
            skill_prompt = PromptCombiner.get_skill_prompt(db, conversation.skill_version_id)
            if skill_prompt:
                parts.append(f"{PromptCombiner.SKILL_SEPARATOR}\n{skill_prompt}")

        # 4. 多 Skill prompt（如果有的话）
        from app.models.skill import Skill
        active_skill_ids = conversation.get_active_skill_ids()
        if active_skill_ids:
            for skill_id in active_skill_ids:
                # 跳过主 Skill（如果已通过 skill_version_id 加载）
                if conversation.skill_id and skill_id == conversation.skill_id:
                    continue

                skill = db.query(Skill).filter(Skill.id == skill_id).first()
                if not skill or not skill.published_version_id:
                    continue
                skill_version = (
                    db.query(SkillVersion)
                    .filter(SkillVersion.id == skill.published_version_id)
                    .first()
                )

                if skill_version and skill_version.system_prompt:
                    from app.services.sandbox_file_manager import SandboxFileManager

                    mount_dirname = SandboxFileManager.resolve_skill_mount_dirname(
                        skill_version.package_path,
                        skill.name,
                    )
                    parts.append(f"{PromptCombiner.SKILL_SEPARATOR}\n")
                    parts.append(f"技能名称：{skill.name}\n")
                    parts.append(f"技能说明：{skill_version.brief_desc or skill.description}\n\n")
                    parts.append(f"执行要求：\n{skill_version.system_prompt}\n\n")
                    parts.append(PromptCombiner._build_skill_sandbox_note(mount_dirname))

        # 组合
        combined = PromptCombiner.SECTION_SEPARATOR.join(parts)

        return combined

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        估算 token 数量（粗略估算：中文约 1.5 字符 = 1 token，英文约 4 字符 = 1 token）

        Args:
            text: 文本内容

        Returns:
            估算的 token 数量
        """
        if not text:
            return 0

        # 简单估算：非 ASCII 字符（中文等）按 1.5 字符 = 1 token，ASCII 字符按 4 字符 = 1 token
        non_ascii_count = sum(1 for c in text if ord(c) > 127)
        ascii_count = len(text) - non_ascii_count

        return int(non_ascii_count / 1.5 + ascii_count / 4)

    @staticmethod
    def truncate_if_needed(prompt: str, max_tokens: Optional[int] = None) -> str:
        """
        如果 prompt 超长，截断低优先级内容

        截断优先级：Skill prompt → 模板 prompt → 默认 prompt

        Args:
            prompt: 组合后的 prompt
            max_tokens: 最大 token 数，默认使用类定义的 MAX_PROMPT_TOKENS

        Returns:
            截断后的 prompt
        """
        max_tokens = max_tokens or PromptCombiner.MAX_PROMPT_TOKENS

        if PromptCombiner.estimate_tokens(prompt) <= max_tokens:
            return prompt

        skill_marker = PromptCombiner.SKILL_SEPARATOR
        skill_pos = prompt.find(skill_marker)

        # 无 Skill 层，直接截断
        if skill_pos < 0:
            return PromptCombiner._truncate_text_to_tokens(prompt, max_tokens)

        # Level1+Level2 基础层（默认+模板）与 Skill 层分离，优先保留 Skill 层
        base_part = prompt[:skill_pos].rstrip()
        skill_part = prompt[skill_pos:].lstrip()

        base_tokens = PromptCombiner.estimate_tokens(base_part)
        sep_tokens = PromptCombiner.estimate_tokens(PromptCombiner.SECTION_SEPARATOR)

        # 即使超长，也优先保留 Skill 层（可截断）
        if base_tokens >= max_tokens:
            return PromptCombiner._truncate_text_to_tokens(base_part, max_tokens)

        remaining_tokens = max_tokens - base_tokens - sep_tokens
        if remaining_tokens <= 0:
            return PromptCombiner._truncate_text_to_tokens(base_part, max_tokens)

        truncated_skill = PromptCombiner._truncate_text_to_tokens(
            skill_part, remaining_tokens
        )
        if not truncated_skill.strip():
            return PromptCombiner._truncate_text_to_tokens(base_part, max_tokens)

        return f"{base_part}{PromptCombiner.SECTION_SEPARATOR}{truncated_skill}"

    @staticmethod
    def _truncate_text_to_tokens(text: str, max_tokens: int) -> str:
        """按估算 token 截断文本。"""
        if not text or max_tokens <= 0:
            return ""
        if PromptCombiner.estimate_tokens(text) <= max_tokens:
            return text

        lo, hi = 0, len(text)
        best = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = text[:mid].rstrip()
            if PromptCombiner.estimate_tokens(candidate) <= max_tokens:
                best = candidate
                lo = mid + 1
            else:
                hi = mid - 1

        if not best:
            return ""
        return best
