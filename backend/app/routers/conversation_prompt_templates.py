import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.message import Message
from app.models.system_prompt_template import SystemPromptTemplate
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.prompt_combiner import PromptCombiner
from app.utils.token_counter import count_tokens
from app.routers.conversations_shared import get_owned_conversation_or_error

logger = logging.getLogger(__name__)
router = APIRouter()


class SwitchPromptTemplateRequest(BaseModel):
    template_id: int


@router.post("/{conversation_id}/prompt-template", response_model=ApiResponse)
def switch_prompt_template(
    conversation_id: int,
    body: SwitchPromptTemplateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template_id = body.template_id
    conv, error = get_owned_conversation_or_error(conversation_id, current_user.id, db)
    if error:
        return error

    template = (
        db.query(SystemPromptTemplate)
        .filter(SystemPromptTemplate.id == template_id)
        .first()
    )
    if not template:
        return ApiResponse.error(40402, "模板不存在")

    if template.visibility == "personal" and template.created_by != current_user.id:
        return ApiResponse.error(40301, "无权限使用此模板")

    old_template_id = conv.prompt_template_id
    conv.prompt_template_id = template_id

    root_system_msg = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == "system",
            Message.parent_id.is_(None),
        )
        .first()
    )

    if root_system_msg:
        new_system_prompt = PromptCombiner.combine_prompts(db, conv, current_user.id)
        new_system_prompt = PromptCombiner.truncate_if_needed(new_system_prompt)
        root_system_msg.content = new_system_prompt
        root_system_msg.token_count = count_tokens(new_system_prompt)

    db.commit()
    db.refresh(conv)

    logger.info(
        f"用户 {current_user.id} 切换对话 {conversation_id} 的模板: {old_template_id} -> {template_id}"
    )

    return ApiResponse.success(
        data={
            "prompt_template_id": conv.prompt_template_id,
            "template_name": template.name,
        }
    )


@router.get("/{conversation_id}/prompt-template", response_model=ApiResponse)
def get_prompt_template(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv, error = get_owned_conversation_or_error(conversation_id, current_user.id, db)
    if error:
        return error

    if not conv.prompt_template_id:
        default_template = (
            db.query(SystemPromptTemplate)
            .filter(SystemPromptTemplate.is_global_default == True)
            .first()
        )

        if default_template:
            return ApiResponse.success(
                data={
                    "prompt_template_id": default_template.id,
                    "template_name": default_template.name,
                    "content": default_template.content,
                    "is_global_default": True,
                }
            )

        return ApiResponse.success(data=None)

    template = (
        db.query(SystemPromptTemplate)
        .filter(SystemPromptTemplate.id == conv.prompt_template_id)
        .first()
    )

    if template:
        return ApiResponse.success(
            data={
                "prompt_template_id": template.id,
                "template_name": template.name,
                "content": template.content,
                "is_global_default": template.is_global_default,
            }
        )

    return ApiResponse.success(data=None)
