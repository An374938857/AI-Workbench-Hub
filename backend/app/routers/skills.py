import os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.skill import Skill, SkillVersion
from app.models.user import User
from app.schemas.base import ApiResponse

router = APIRouter()


@router.get("")
def list_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    tag_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    query = db.query(Skill).filter(Skill.status == "published")

    if keyword:
        like = f"%{keyword}%"
        query = query.filter(Skill.name.like(like))

    if tag_id:
        query = query.filter(Skill.tags.any(id=tag_id))

    total = query.count()
    items = (
        query.order_by(Skill.sort_weight.desc(), Skill.use_count.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ApiResponse.success(data={
        "items": [_skill_card(s) for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/{skill_id}")
def get_skill_detail(
    skill_id: int,
    db: Session = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.status == "published").first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在或未发布")

    pub = skill.published_version
    if not pub:
        return ApiResponse.error(40201, "Skill 版本异常")

    version_logs = (
        db.query(SkillVersion)
        .filter(SkillVersion.skill_id == skill_id, SkillVersion.change_log.isnot(None))
        .order_by(SkillVersion.version_number.desc())
        .all()
    )

    return ApiResponse.success(data={
        "id": skill.id,
        "name": skill.name,
        "icon_url": f"/api/files/icons/{os.path.basename(skill.icon_path)}" if skill.icon_path else None,
        "icon_emoji": skill.icon_emoji,
        "brief_desc": pub.brief_desc,
        "detail_desc": pub.detail_desc,
        "tags": [{"id": t.id, "name": t.name} for t in (skill.tags or [])],
        "usage_example": pub.usage_example,
        "system_prompt": pub.system_prompt,
        "use_count": skill.use_count,
        "creator_name": skill.creator.display_name if skill.creator else None,
        "current_version": pub.version_number,
        "version_logs": [
            {
                "version": v.version_number,
                "change_log": v.change_log,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in version_logs
        ],
    })


def _skill_card(s: Skill) -> dict:
    pub = s.published_version
    return {
        "id": s.id,
        "name": s.name,
        "icon_url": f"/api/files/icons/{os.path.basename(s.icon_path)}" if s.icon_path else None,
        "icon_emoji": s.icon_emoji,
        "brief_desc": pub.brief_desc if pub else "",
        "tags": [{"id": t.id, "name": t.name} for t in (s.tags or [])],
        "use_count": s.use_count,
        "creator_name": s.creator.display_name if s.creator else None,
        "model_provider_id": pub.model_provider_id if pub else None,
        "model_name": pub.model_name if pub else None,
    }
