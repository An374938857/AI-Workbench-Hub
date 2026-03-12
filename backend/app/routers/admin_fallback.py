"""Fallback 配置管理路由"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.deps import get_db, require_role
from app.models.model_fallback import ModelFallbackConfig
from app.models.user import User
from app.schemas.base import ApiResponse

router = APIRouter()


class FallbackChainItem(BaseModel):
    provider_id: int
    model_name: str


class CreateFallbackConfigRequest(BaseModel):
    source_provider_id: Optional[int] = None
    source_model_name: Optional[str] = None
    fallback_chain: list[FallbackChainItem]
    priority: int = 0


class UpdateFallbackConfigRequest(BaseModel):
    fallback_chain: Optional[list[FallbackChainItem]] = None
    priority: Optional[int] = None
    is_enabled: Optional[bool] = None


@router.get("")
def list_fallback_configs(
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    """获取所有 Fallback 配置"""
    configs = db.query(ModelFallbackConfig).order_by(
        ModelFallbackConfig.priority.desc(),
        ModelFallbackConfig.id
    ).all()
    
    return ApiResponse.success(data=[
        {
            "id": c.id,
            "source_provider_id": c.source_provider_id,
            "source_model_name": c.source_model_name,
            "fallback_chain": c.fallback_chain,
            "priority": c.priority,
            "is_enabled": c.is_enabled,
            "created_at": c.created_at.isoformat(),
        }
        for c in configs
    ])


@router.post("")
def create_fallback_config(
    request: CreateFallbackConfigRequest,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    """创建 Fallback 配置"""
    config = ModelFallbackConfig(
        source_provider_id=request.source_provider_id,
        source_model_name=request.source_model_name,
        fallback_chain=[item.model_dump() for item in request.fallback_chain],
        priority=request.priority,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    
    return ApiResponse.success(data={"id": config.id})


@router.put("/{config_id}")
def update_fallback_config(
    config_id: int,
    request: UpdateFallbackConfigRequest,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    """更新 Fallback 配置"""
    config = db.query(ModelFallbackConfig).filter(
        ModelFallbackConfig.id == config_id
    ).first()
    
    if not config:
        return ApiResponse.error(40401, "配置不存在")
    
    if request.fallback_chain is not None:
        config.fallback_chain = [item.model_dump() for item in request.fallback_chain]
    if request.priority is not None:
        config.priority = request.priority
    if request.is_enabled is not None:
        config.is_enabled = request.is_enabled
    
    db.commit()
    return ApiResponse.success()


@router.delete("/{config_id}")
def delete_fallback_config(
    config_id: int,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    """删除 Fallback 配置"""
    config = db.query(ModelFallbackConfig).filter(
        ModelFallbackConfig.id == config_id
    ).first()
    
    if not config:
        return ApiResponse.error(40401, "配置不存在")
    
    db.delete(config)
    db.commit()
    return ApiResponse.success()
