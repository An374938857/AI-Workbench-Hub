from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user, require_role
from app.models.scene_tag import SceneTag
from app.models.skill import skill_tags
from app.models.user import User
from app.schemas.base import ApiResponse

router = APIRouter()


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    sort_order: int = 0


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


def _tag_to_dict(tag: SceneTag) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "sort_order": tag.sort_order,
        "is_active": tag.is_active,
    }


@router.get("")
def list_tags(
    db: Session = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    tags = db.query(SceneTag).order_by(SceneTag.sort_order.desc(), SceneTag.id).all()
    return ApiResponse.success(data=[_tag_to_dict(t) for t in tags])


@router.post("")
def create_tag(
    body: TagCreate,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    if db.query(SceneTag).filter(SceneTag.name == body.name).first():
        return ApiResponse.error(40200, f"标签名称 '{body.name}' 已存在")

    tag = SceneTag(name=body.name, sort_order=body.sort_order)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return ApiResponse.success(data=_tag_to_dict(tag), message="标签创建成功")


@router.put("/{tag_id}")
def update_tag(
    tag_id: int,
    body: TagUpdate,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    tag = db.query(SceneTag).filter(SceneTag.id == tag_id).first()
    if not tag:
        return ApiResponse.error(40201, "标签不存在")

    if body.name is not None:
        dup = db.query(SceneTag).filter(SceneTag.name == body.name, SceneTag.id != tag_id).first()
        if dup:
            return ApiResponse.error(40200, f"标签名称 '{body.name}' 已存在")
        tag.name = body.name
    if body.sort_order is not None:
        tag.sort_order = body.sort_order
    if body.is_active is not None:
        tag.is_active = body.is_active

    db.commit()
    db.refresh(tag)
    return ApiResponse.success(data=_tag_to_dict(tag), message="标签更新成功")


@router.delete("/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    tag = db.query(SceneTag).filter(SceneTag.id == tag_id).first()
    if not tag:
        return ApiResponse.error(40201, "标签不存在")

    usage_count = db.query(skill_tags).filter(skill_tags.c.tag_id == tag_id).count()
    if usage_count > 0:
        return ApiResponse.error(40202, f"该标签正被 {usage_count} 个 Skill 使用，无法删除")

    db.delete(tag)
    db.commit()
    return ApiResponse.success(message="标签删除成功")
