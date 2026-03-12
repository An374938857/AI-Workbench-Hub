import logging
import os

from sqlalchemy.orm import Session

from app.models.skill import Skill, SkillVersion

logger = logging.getLogger(__name__)


def check_skill_package_paths(db: Session) -> dict:
    """
    启动自检：扫描 SkillVersion.package_path，记录缺失路径。
    """
    rows = (
        db.query(
            SkillVersion.id,
            SkillVersion.skill_id,
            SkillVersion.package_path,
            Skill.name,
        )
        .join(Skill, Skill.id == SkillVersion.skill_id)
        .filter(SkillVersion.package_path.isnot(None))
        .all()
    )

    missing_items: list[dict] = []

    for version_id, skill_id, package_path, skill_name in rows:
        path = (package_path or "").strip()
        if not path:
            continue
        if not os.path.isdir(path):
            missing_items.append(
                {
                    "version_id": version_id,
                    "skill_id": skill_id,
                    "skill_name": skill_name,
                    "package_path": path,
                }
            )

    summary = {
        "checked_count": len(rows),
        "missing_count": len(missing_items),
        "missing_items": missing_items,
    }

    if missing_items:
        logger.warning(
            "Skill 包路径自检发现缺失: checked=%s, missing=%s",
            summary["checked_count"],
            summary["missing_count"],
        )
        for item in missing_items:
            logger.warning(
                "缺失 Skill 包: skill_id=%s, skill_name=%s, version_id=%s, path=%s",
                item["skill_id"],
                item["skill_name"],
                item["version_id"],
                item["package_path"],
            )
    else:
        logger.info(
            "Skill 包路径自检通过: checked=%s, missing=0",
            summary["checked_count"],
        )

    return summary
