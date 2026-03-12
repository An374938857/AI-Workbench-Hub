"""对话标签管理路由"""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.conversation_tag import ConversationTag, ConversationTagRelation
from app.models.user import User
from app.schemas.base import ApiResponse
from app.schemas.tag import TagCreate, TagUpdate

router = APIRouter()

MAX_TAGS_PER_USER = 20
MAX_TAGS_PER_CONVERSATION = 5


@router.get("")
def list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tags = (
        db.query(ConversationTag)
        .filter(ConversationTag.user_id == current_user.id)
        .order_by(ConversationTag.sort_order)
        .all()
    )
    result = []
    for t in tags:
        count = (
            db.query(func.count(ConversationTagRelation.id))
            .filter(ConversationTagRelation.tag_id == t.id)
            .scalar()
        ) or 0
        result.append({
            "id": t.id,
            "name": t.name,
            "color": t.color,
            "sort_order": t.sort_order,
            "conversation_count": count,
        })
    return ApiResponse.success(data=result)


@router.post("")
def create_tag(
    body: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing_count = (
        db.query(func.count(ConversationTag.id))
        .filter(ConversationTag.user_id == current_user.id)
        .scalar()
    ) or 0
    if existing_count >= MAX_TAGS_PER_USER:
        return ApiResponse.error(40500, f"标签数量已达上限（{MAX_TAGS_PER_USER}）")

    dup = (
        db.query(ConversationTag)
        .filter(
            ConversationTag.user_id == current_user.id,
            ConversationTag.name == body.name,
        )
        .first()
    )
    if dup:
        return ApiResponse.error(40501, "标签名称已存在")

    max_order = (
        db.query(func.max(ConversationTag.sort_order))
        .filter(ConversationTag.user_id == current_user.id)
        .scalar()
    )
    tag = ConversationTag(
        user_id=current_user.id,
        name=body.name,
        color=body.color,
        sort_order=(max_order + 1) if max_order is not None else 0,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)

    return ApiResponse.success(data={
        "id": tag.id, "name": tag.name, "color": tag.color, "sort_order": tag.sort_order,
    })


@router.put("/{tag_id}")
def update_tag(
    tag_id: int,
    body: TagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tag = db.query(ConversationTag).filter(
        ConversationTag.id == tag_id,
        ConversationTag.user_id == current_user.id,
    ).first()
    if not tag:
        return ApiResponse.error(40502, "标签不存在")

    if body.name is not None and body.name != tag.name:
        dup = db.query(ConversationTag).filter(
            ConversationTag.user_id == current_user.id,
            ConversationTag.name == body.name,
            ConversationTag.id != tag_id,
        ).first()
        if dup:
            return ApiResponse.error(40501, "标签名称已存在")
        tag.name = body.name
    if body.color is not None:
        tag.color = body.color
    if body.sort_order is not None:
        tag.sort_order = body.sort_order

    db.commit()
    return ApiResponse.success(data={
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
        "sort_order": tag.sort_order,
    })


@router.delete("/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tag = db.query(ConversationTag).filter(
        ConversationTag.id == tag_id,
        ConversationTag.user_id == current_user.id,
    ).first()
    if not tag:
        return ApiResponse.error(40502, "标签不存在")

    db.delete(tag)
    db.commit()
    return ApiResponse.success(message="标签已删除")
