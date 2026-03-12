"""
提示词模板管理路由
Prompt 模板 CRUD、收藏、设置默认
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.deps import get_current_user
from app.models.conversation import Conversation
from app.models.prompt_template_version import PromptTemplateVersion
from app.models.system_prompt_template import SystemPromptTemplate
from app.models.user_prompt_favorite import UserPromptFavorite
from app.models.user import User
from app.schemas.base import ApiResponse
from app.schemas.prompt_template import (
    SystemPromptTemplateCreate,
    SystemPromptTemplateUpdate,
    SystemPromptTemplateResponse,
    SystemPromptTemplateDuplicateRequest,
    PromptTemplateStatsResponse,
    PromptTemplateVersionCreateRequest,
    PromptTemplateVersionResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _is_admin(user: User) -> bool:
    # 兼容历史代码：优先读取可能存在的 is_admin 属性，缺失时按 role 判断
    return bool(getattr(user, "is_admin", False) or user.role == "admin")


def _can_view_template(template: SystemPromptTemplate, user: User) -> bool:
    if template.visibility == "public":
        return True
    return template.created_by == user.id or _is_admin(user)


def _can_edit_template(template: SystemPromptTemplate, user: User) -> bool:
    if template.is_builtin:
        return False
    if template.visibility == "personal":
        return template.created_by == user.id
    return _is_admin(user)


def _build_template_response(
    template: SystemPromptTemplate,
    is_favorited: bool = False,
) -> SystemPromptTemplateResponse:
    return SystemPromptTemplateResponse(
        id=template.id,
        name=template.name,
        category=template.category,
        content=template.content,
        is_default=template.is_default,
        priority=template.priority,
        is_builtin=template.is_builtin,
        visibility=template.visibility,
        is_global_default=template.is_global_default,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
        is_favorited=is_favorited,
    )


def _version_table_ready(db: Session) -> bool:
    try:
        return inspect(db.bind).has_table("prompt_template_versions")
    except Exception:
        return False


def _next_version_no(db: Session, template_id: int) -> int:
    current_max = (
        db.query(func.max(PromptTemplateVersion.version_no))
        .filter(PromptTemplateVersion.template_id == template_id)
        .scalar()
    )
    return int(current_max or 0) + 1


def _create_version_snapshot(
    db: Session,
    template: SystemPromptTemplate,
    created_by: Optional[int],
    note: Optional[str] = None,
) -> Optional[PromptTemplateVersion]:
    if not _version_table_ready(db):
        return None
    version = PromptTemplateVersion(
        template_id=template.id,
        version_no=_next_version_no(db, template.id),
        name=template.name,
        category=template.category,
        content=template.content,
        priority=template.priority,
        visibility=template.visibility,
        note=note,
        created_by=created_by,
    )
    db.add(version)
    return version


@router.get("", response_model=ApiResponse)
def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, description="分类筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板列表（支持筛选、搜索、收藏优先）"""
    query = db.query(SystemPromptTemplate)

    # 权限过滤：公开模板或用户自己的模板
    query = query.filter(
        (SystemPromptTemplate.visibility == "public")
        | (SystemPromptTemplate.created_by == current_user.id)
    )

    # 分类筛选
    if category:
        query = query.filter(SystemPromptTemplate.category == category)

    # 关键词搜索
    if search:
        query = query.filter(SystemPromptTemplate.name.contains(search))

    # 获取用户收藏的模板ID
    favorited_ids = set(
        row.template_id
        for row in db.query(UserPromptFavorite).filter(
            UserPromptFavorite.user_id == current_user.id
        ).all()
    )

    # 统计总数
    total = query.count()

    # 分页
    offset = (page - 1) * page_size
    templates = (
        query.order_by(SystemPromptTemplate.is_global_default.desc(), SystemPromptTemplate.priority.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # 构建响应，收藏的排在前面
    template_list = []
    favorited_templates = []
    other_templates = []

    for t in templates:
        is_favorited = t.id in favorited_ids
        resp = SystemPromptTemplateResponse(
            id=t.id,
            name=t.name,
            category=t.category,
            content=t.content,
            is_default=t.is_default,
            priority=t.priority,
            is_builtin=t.is_builtin,
            visibility=t.visibility,
            is_global_default=t.is_global_default,
            created_by=t.created_by,
            created_at=t.created_at,
            updated_at=t.updated_at,
            is_favorited=is_favorited,
        )
        if is_favorited:
            favorited_templates.append(resp)
        else:
            other_templates.append(resp)

    template_list = favorited_templates + other_templates

    return ApiResponse.success(data={
        "templates": template_list,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("", response_model=ApiResponse)
def create_template(
    data: SystemPromptTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建模板"""
    template = SystemPromptTemplate(
        name=data.name,
        category=data.category,
        content=data.content,
        priority=data.priority,
        visibility=data.visibility,
        created_by=current_user.id,
    )
    db.add(template)
    db.flush()
    _create_version_snapshot(
        db=db,
        template=template,
        created_by=current_user.id,
        note="初始版本",
    )
    db.commit()
    db.refresh(template)

    logger.info(f"用户 {current_user.id} 创建模板: {template.id}")

    return ApiResponse.success(data=_build_template_response(template, is_favorited=False))


@router.get("/{template_id}", response_model=ApiResponse)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板详情"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    # 权限检查
    if not _can_view_template(template, current_user):
        return ApiResponse.error(40301, "无权限访问")

    # 检查是否收藏
    is_favorited = db.query(UserPromptFavorite).filter(
        UserPromptFavorite.user_id == current_user.id,
        UserPromptFavorite.template_id == template_id,
    ).first() is not None

    return ApiResponse.success(data=_build_template_response(template, is_favorited=is_favorited))


@router.put("/{template_id}", response_model=ApiResponse)
def update_template(
    template_id: int,
    data: SystemPromptTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑模板"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    # 权限检查：内置模板不可修改，个人模板只有创建者可以修改，公开模板只有管理员可以修改
    if template.is_builtin:
        return ApiResponse.error(40302, "内置模板不可修改")
    if not _can_edit_template(template, current_user):
        return ApiResponse.error(40301, "无权限修改")

    _create_version_snapshot(
        db=db,
        template=template,
        created_by=current_user.id,
        note="编辑前快照",
    )

    # 更新字段
    if data.name is not None:
        template.name = data.name
    if data.category is not None:
        template.category = data.category
    if data.content is not None:
        template.content = data.content
    if data.priority is not None:
        template.priority = data.priority
    if data.visibility is not None:
        template.visibility = data.visibility
    if data.is_default is not None:
        template.is_default = data.is_default

    db.commit()
    db.refresh(template)

    # 检查收藏状态
    is_favorited = db.query(UserPromptFavorite).filter(
        UserPromptFavorite.user_id == current_user.id,
        UserPromptFavorite.template_id == template_id,
    ).first() is not None

    return ApiResponse.success(data=_build_template_response(template, is_favorited=is_favorited))


@router.delete("/{template_id}", response_model=ApiResponse)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除模板"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    # 权限检查
    if template.is_builtin:
        return ApiResponse.error(40302, "内置模板不可删除")

    if not _can_edit_template(template, current_user):
        return ApiResponse.error(40301, "无权限删除")

    # 删除收藏记录
    db.query(UserPromptFavorite).filter(
        UserPromptFavorite.template_id == template_id
    ).delete()
    if _version_table_ready(db):
        db.query(PromptTemplateVersion).filter(
            PromptTemplateVersion.template_id == template_id
        ).delete()

    # 删除模板
    db.delete(template)
    db.commit()

    logger.info(f"用户 {current_user.id} 删除模板: {template_id}")

    return ApiResponse.success(message="删除成功")


@router.post("/{template_id}/set-default", response_model=ApiResponse)
def set_global_default(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """设置全局默认（管理员）"""
    if not _is_admin(current_user):
        return ApiResponse.error(40301, "只有管理员可以设置全局默认")

    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    # 清除其他全局默认
    db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.is_global_default == True
    ).update({"is_global_default": False})

    # 设置当前模板为全局默认
    template.is_global_default = True
    db.commit()

    logger.info(f"管理员设置全局默认模板: {template_id}")

    return ApiResponse.success(message="设置成功")


@router.post("/{template_id}/duplicate", response_model=ApiResponse)
def duplicate_template(
    template_id: int,
    data: SystemPromptTemplateDuplicateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """复制模板"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    if not _can_view_template(template, current_user):
        return ApiResponse.error(40301, "无权限复制此模板")

    duplicate_name = data.name or f"{template.name}（副本）"
    new_template = SystemPromptTemplate(
        name=duplicate_name,
        category=template.category,
        content=template.content,
        priority=template.priority,
        visibility="personal",
        created_by=current_user.id,
    )
    db.add(new_template)
    db.flush()

    _create_version_snapshot(
        db=db,
        template=new_template,
        created_by=current_user.id,
        note=f"复制自模板#{template_id}",
    )
    db.commit()
    db.refresh(new_template)

    return ApiResponse.success(data=_build_template_response(new_template, is_favorited=False))


@router.get("/{template_id}/stats", response_model=ApiResponse)
def get_template_stats(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板统计信息"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    if not _can_view_template(template, current_user):
        return ApiResponse.error(40301, "无权限访问")

    conversation_count = db.query(func.count(Conversation.id)).filter(
        Conversation.prompt_template_id == template_id
    ).scalar() or 0

    last_used_at = db.query(func.max(Conversation.updated_at)).filter(
        Conversation.prompt_template_id == template_id
    ).scalar()

    favorite_count = db.query(func.count(UserPromptFavorite.id)).filter(
        UserPromptFavorite.template_id == template_id
    ).scalar() or 0

    version_count = 0
    if _version_table_ready(db):
        try:
            version_count = db.query(func.count(PromptTemplateVersion.id)).filter(
                PromptTemplateVersion.template_id == template_id
            ).scalar() or 0
        except (ProgrammingError, OperationalError):
            version_count = 0

    return ApiResponse.success(data=PromptTemplateStatsResponse(
        conversation_count=conversation_count,
        favorite_count=favorite_count,
        last_used_at=last_used_at,
        version_count=version_count,
    ))


@router.get("/{template_id}/versions", response_model=ApiResponse)
def list_template_versions(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板版本列表"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    if not _can_view_template(template, current_user):
        return ApiResponse.error(40301, "无权限访问")

    if not _version_table_ready(db):
        return ApiResponse.success(data=[])

    try:
        versions = db.query(PromptTemplateVersion).filter(
            PromptTemplateVersion.template_id == template_id
        ).order_by(PromptTemplateVersion.version_no.desc()).all()
    except (ProgrammingError, OperationalError):
        return ApiResponse.success(data=[])

    return ApiResponse.success(data=[
        PromptTemplateVersionResponse(
            id=v.id,
            template_id=v.template_id,
            version_no=v.version_no,
            name=v.name,
            category=v.category,
            content=v.content,
            priority=v.priority,
            visibility=v.visibility,
            note=v.note,
            created_by=v.created_by,
            created_at=v.created_at,
        )
        for v in versions
    ])


@router.post("/{template_id}/versions", response_model=ApiResponse)
def create_template_version(
    template_id: int,
    data: PromptTemplateVersionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建模板版本快照"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    if not _can_edit_template(template, current_user):
        return ApiResponse.error(40301, "无权限创建版本")

    if not _version_table_ready(db):
        return ApiResponse.error(50011, "版本功能未初始化，请执行 alembic upgrade head")

    version = _create_version_snapshot(
        db=db,
        template=template,
        created_by=current_user.id,
        note=data.note or "手动保存版本",
    )
    if not version:
        return ApiResponse.error(50011, "版本功能未初始化，请执行 alembic upgrade head")
    db.commit()
    db.refresh(version)

    return ApiResponse.success(data=PromptTemplateVersionResponse(
        id=version.id,
        template_id=version.template_id,
        version_no=version.version_no,
        name=version.name,
        category=version.category,
        content=version.content,
        priority=version.priority,
        visibility=version.visibility,
        note=version.note,
        created_by=version.created_by,
        created_at=version.created_at,
    ))


@router.post("/{template_id}/restore/{version_id}", response_model=ApiResponse)
def restore_template_version(
    template_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """恢复模板到指定版本"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    if not _can_edit_template(template, current_user):
        return ApiResponse.error(40301, "无权限恢复版本")

    if not _version_table_ready(db):
        return ApiResponse.error(50011, "版本功能未初始化，请执行 alembic upgrade head")

    version = db.query(PromptTemplateVersion).filter(
        PromptTemplateVersion.id == version_id,
        PromptTemplateVersion.template_id == template_id,
    ).first()
    if not version:
        return ApiResponse.error(40402, "版本不存在")

    _create_version_snapshot(
        db=db,
        template=template,
        created_by=current_user.id,
        note=f"恢复前快照，目标版本 v{version.version_no}",
    )

    template.name = version.name
    template.category = version.category
    template.content = version.content
    template.priority = version.priority
    template.visibility = version.visibility

    db.commit()
    db.refresh(template)

    is_favorited = db.query(UserPromptFavorite).filter(
        UserPromptFavorite.user_id == current_user.id,
        UserPromptFavorite.template_id == template_id,
    ).first() is not None

    return ApiResponse.success(
        message=f"已恢复到版本 v{version.version_no}",
        data=_build_template_response(template, is_favorited=is_favorited),
    )


@router.post("/{template_id}/favorite", response_model=ApiResponse)
def toggle_favorite(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """收藏/取消收藏模板"""
    template = db.query(SystemPromptTemplate).filter(
        SystemPromptTemplate.id == template_id
    ).first()

    if not template:
        return ApiResponse.error(40401, "模板不存在")

    # 检查是否已收藏
    favorite = db.query(UserPromptFavorite).filter(
        UserPromptFavorite.user_id == current_user.id,
        UserPromptFavorite.template_id == template_id,
    ).first()

    if favorite:
        # 取消收藏
        db.delete(favorite)
        db.commit()
        return ApiResponse.success(message="已取消收藏", data={"is_favorited": False})
    else:
        # 添加收藏
        new_favorite = UserPromptFavorite(
            user_id=current_user.id,
            template_id=template_id,
        )
        db.add(new_favorite)
        db.commit()
        return ApiResponse.success(message="收藏成功", data={"is_favorited": True})
