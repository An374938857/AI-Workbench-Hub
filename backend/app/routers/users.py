from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_db, require_role, get_current_user
from app.models.conversation import Conversation
from app.models.conversation_tag import ConversationTag
from app.models.custom_command import CustomCommand
from app.models.feedback import Feedback
from app.models.mcp import Mcp
from app.models.mcp_call_log import McpCallLog
from app.models.skill import Skill
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.models.usage_log import UsageLog
from app.models.user_sort_preference import UserSortPreference
from app.schemas.base import ApiResponse
from app.schemas.user import UserCreate, UserUpdate, ResetPasswordRequest
from app.utils.security import hash_password

from pydantic import BaseModel as PydanticBaseModel

router = APIRouter()


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "is_approved": user.is_approved,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.get("")
def get_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    query = db.query(User)
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            (User.username.like(like_pattern)) | (User.display_name.like(like_pattern))
        )
    total = query.count()
    items = query.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    return ApiResponse.success(data={
        "items": [_user_to_dict(u) for u in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("")
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        return ApiResponse.error(40200, f"用户名 '{body.username}' 已存在")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ApiResponse.success(data=_user_to_dict(user), message="用户创建成功")


@router.put("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ApiResponse.error(40201, "用户不存在")

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)
    return ApiResponse.success(data=_user_to_dict(user), message="用户更新成功")


@router.put("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ApiResponse.error(40201, "用户不存在")

    user.password_hash = hash_password(body.new_password)
    db.commit()
    return ApiResponse.success(message="密码重置成功")


@router.put("/{user_id}/approve")
def approve_user(
    user_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ApiResponse.error(40201, "用户不存在")
    if user.is_approved:
        return ApiResponse.error(40203, "该用户已审核通过，无需重复审核")

    user.is_approved = True
    db.commit()
    db.refresh(user)
    return ApiResponse.success(data=_user_to_dict(user), message="用户审核通过")


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    force_transfer: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    if user_id == current_user.id:
        return ApiResponse.error(40202, "不能删除自己的账号")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ApiResponse.error(40201, "用户不存在")

    skill_count = db.query(Skill).filter(Skill.creator_id == user_id).count()
    mcp_count = db.query(Mcp).filter(Mcp.creator_id == user_id).count()
    has_related_owner_data = skill_count > 0 or mcp_count > 0

    if has_related_owner_data and not force_transfer:
        return ApiResponse.error(
            40204,
            f"该用户存在创建者关联数据（Skill: {skill_count}，MCP: {mcp_count}），请确认是否转移到超级管理员后再删除",
        )

    try:
        if has_related_owner_data:
            transfer_admin = (
                db.query(User)
                .filter(User.role == "admin", User.id != user_id)
                .order_by(User.id.asc())
                .first()
            )
            if not transfer_admin:
                return ApiResponse.error(40205, "未找到可接收归属的超级管理员，无法删除该用户")

            db.query(Skill).filter(Skill.creator_id == user_id).update(
                {"creator_id": transfer_admin.id}, synchronize_session=False
            )
            db.query(Mcp).filter(Mcp.creator_id == user_id).update(
                {"creator_id": transfer_admin.id}, synchronize_session=False
            )

        # 清理与用户绑定的业务数据，避免外键约束导致删除失败。
        db.query(UserSortPreference).filter(UserSortPreference.user_id == user_id).delete(synchronize_session=False)
        db.query(CustomCommand).filter(CustomCommand.user_id == user_id).delete(synchronize_session=False)
        db.query(ConversationTag).filter(ConversationTag.user_id == user_id).delete(synchronize_session=False)

        db.query(UsageLog).filter(UsageLog.user_id == user_id).delete(synchronize_session=False)
        db.query(McpCallLog).filter(McpCallLog.user_id == user_id).delete(synchronize_session=False)
        db.query(Feedback).filter(Feedback.user_id == user_id).delete(synchronize_session=False)
        db.query(UploadedFile).filter(UploadedFile.user_id == user_id).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.user_id == user_id).delete(synchronize_session=False)

        db.delete(user)
        db.commit()
        return ApiResponse.success(message="用户删除成功")
    except IntegrityError:
        db.rollback()
        return ApiResponse.error(50010, "用户存在关联数据，暂无法删除，请联系管理员处理")


@router.get("/{user_id}/delete-check")
def delete_user_check(
    user_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ApiResponse.error(40201, "用户不存在")

    skill_count = db.query(Skill).filter(Skill.creator_id == user_id).count()
    mcp_count = db.query(Mcp).filter(Mcp.creator_id == user_id).count()
    return ApiResponse.success(data={
        "skill_count": skill_count,
        "mcp_count": mcp_count,
        "has_related_owner_data": skill_count > 0 or mcp_count > 0,
    })


class AutoRouteToggle(PydanticBaseModel):
    enabled: bool


@router.get("/me/auto-route")
def get_auto_route(
    current_user: User = Depends(get_current_user),
):
    return ApiResponse.success(data={"auto_route_enabled": current_user.auto_route_enabled})


@router.patch("/me/auto-route")
def toggle_auto_route(
    body: AutoRouteToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.auto_route_enabled = body.enabled
    db.commit()
    return ApiResponse.success(data={"auto_route_enabled": current_user.auto_route_enabled})
