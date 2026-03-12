"""模型相关路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.deps import get_db, get_current_user
from app.models.model_provider import ModelProvider, ModelItem
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.skill import Skill
from app.schemas.base import ApiResponse
from app.models.user import User

router = APIRouter(tags=["models"])


class SwitchModelRequest(BaseModel):
    provider_id: int
    model_name: str


@router.get("/default")
async def get_default_model(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取全局默认模型（仅返回已启用模型）。"""
    model = (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(
            ModelItem.is_default == True,
            ModelItem.is_enabled == True,
            ModelProvider.is_enabled == True,
        )
        .first()
    )
    if not model:
        return ApiResponse.success(data=None)

    provider = model.provider
    return ApiResponse.success(data={
        "provider_id": model.provider_id,
        "provider_name": provider.provider_name if provider else "",
        "model_name": model.model_name,
        "display_name": f"{provider.provider_name if provider else ''} / {model.model_name}",
    })


@router.get("/available")
async def get_available_models(
    conversation_id: int = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """获取所有已启用的模型列表，按提供商分组。传入 conversation_id 时标记推荐模型。"""
    from app.constants.model_tags import SCENE_TO_CAPABILITY

    # 计算推荐能力标签
    recommended_caps: set[str] = set()
    if conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv and conv.skill_id:
            skill = db.query(Skill).filter(Skill.id == conv.skill_id).first()
            if skill:
                for tag in (skill.tags or []):
                    recommended_caps.update(SCENE_TO_CAPABILITY.get(tag.name, []))

    providers = db.query(ModelProvider).filter(ModelProvider.is_enabled == True).all()
    
    result = []
    for provider in providers:
        models = db.query(ModelItem).filter(
            ModelItem.provider_id == provider.id,
            ModelItem.is_enabled == True
        ).all()
        
        if models:
            result.append({
                "provider_id": provider.id,
                "provider_name": provider.provider_name,
                "protocol_type": provider.protocol_type,
                "models": [
                    {
                        "model_name": model.model_name,
                        "display_name": model.model_name,
                        "context_window": model.context_window,
                        "capability_tags": model.capability_tags or [],
                        "speed_rating": model.speed_rating,
                        "cost_rating": model.cost_rating,
                        "description": model.description,
                        "max_output_tokens": model.max_output_tokens,
                        "is_default": model.is_default,
                        "is_recommended": bool(recommended_caps and set(model.capability_tags or []) & recommended_caps),
                    }
                    for model in models
                ]
            })
    
    return ApiResponse.success(data={"providers": result})


@router.post("/conversations/{conversation_id}/switch-model")
async def switch_conversation_model(
    conversation_id: int,
    request: SwitchModelRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    切换对话使用的模型
    
    - 更新 conversation.current_provider_id 和 current_model_name
    - 插入系统通知消息
    """
    # 验证对话存在且属于当前用户
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    
    # 验证提供商和模型存在且已启用
    provider = db.query(ModelProvider).filter(
        ModelProvider.id == request.provider_id,
        ModelProvider.is_enabled == True
    ).first()
    
    if not provider:
        raise HTTPException(status_code=404, detail="提供商不存在或未启用")
    
    model = db.query(ModelItem).filter(
        ModelItem.provider_id == request.provider_id,
        ModelItem.model_name == request.model_name,
        ModelItem.is_enabled == True
    ).first()
    
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在或未启用")
    
    # 更新对话模型
    old_model = conversation.current_model_name or "默认模型"
    conversation.current_provider_id = request.provider_id
    conversation.current_model_name = request.model_name
    
    # 插入系统通知消息
    notice_message = Message(
        conversation_id=conversation_id,
        role="system_notice",
        content=f"已切换模型：{old_model} → {provider.provider_name}/{request.model_name}",
        created_at=datetime.now()
    )
    db.add(notice_message)
    db.commit()
    
    return ApiResponse.success(data={
        "provider_name": provider.provider_name,
        "model_name": request.model_name,
    }, message=f"已切换到 {provider.provider_name}/{request.model_name}")
