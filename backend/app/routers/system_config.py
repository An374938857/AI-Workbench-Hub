"""
系统配置管理路由（管理员权限）
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user, require_role
from app.models.user import User
from app.models.system_config import SystemConfig
from app.schemas.system_config import SystemConfigUpdate
from app.schemas.base import ApiResponse

router = APIRouter()


@router.get("/system-config", response_model=ApiResponse)
def get_all_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """获取所有系统配置（管理员）"""
    configs = db.query(SystemConfig).all()
    config_list = []
    for config in configs:
        config_list.append({
            "id": config.id,
            "key": config.key,
            "value": config.get_value(),
            "value_type": config.value_type,
            "description": config.description,
            "updated_by": config.updated_by,
            "updated_at": config.updated_at.isoformat()
        })
    return ApiResponse.success(data=config_list)


@router.get("/system-config/{key}", response_model=ApiResponse)
def get_config(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取指定系统配置"""
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"配置 {key} 不存在"
        )

    return ApiResponse.success(data={
        "id": config.id,
        "key": config.key,
        "value": config.get_value(),
        "value_type": config.value_type,
        "description": config.description,
        "updated_by": config.updated_by,
        "updated_at": config.updated_at.isoformat()
    })


@router.put("/system-config", response_model=ApiResponse)
def update_config(
    request: SystemConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """更新系统配置（管理员）"""
    config = db.query(SystemConfig).filter(SystemConfig.key == request.key).first()

    if config:
        # 更新现有配置
        config.set_value(request.value)
        if request.description is not None:
            config.description = request.description
        config.updated_by = current_user.id
        db.commit()
        db.refresh(config)
    else:
        # 创建新配置
        config = SystemConfig(
            key=request.key,
            description=request.description
        )
        config.set_value(request.value)
        config.updated_by = current_user.id
        db.add(config)
        db.commit()
        db.refresh(config)

    return ApiResponse.success(data={
        "id": config.id,
        "key": config.key,
        "value": config.get_value(),
        "value_type": config.value_type,
        "description": config.description,
        "updated_by": config.updated_by,
        "updated_at": config.updated_at.isoformat()
    })