import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.message import Message
from app.models.skill import Skill
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.skill_activation_manager import SkillActivationManager
from app.routers.conversations_shared import (
    get_conversation_active_skills,
    get_owned_conversation_or_error,
    refresh_root_system_prompt,
)

router = APIRouter()


@router.get("/{conversation_id}/skills", response_model=ApiResponse)
def get_active_skills(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skills = SkillActivationManager.get_active_skills(
        conversation_id, db, current_user.id
    )
    return ApiResponse.success(data=skills)


@router.post("/{conversation_id}/skills", response_model=ApiResponse)
def activate_skill(
    conversation_id: int,
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = SkillActivationManager.activate_skill(
        skill_id,
        conversation_id,
        db,
        current_user.id,
        source=SkillActivationManager.SOURCE_MANUAL_API,
    )
    if result.get("success"):
        refresh_root_system_prompt(conversation_id, db, current_user.id)
        db.commit()
    return ApiResponse.success(data=result)


@router.post("/{conversation_id}/skills/{skill_id}/confirm", response_model=ApiResponse)
def confirm_skill_activation(
    conversation_id: int,
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv, error = get_owned_conversation_or_error(conversation_id, current_user.id, db)
    if error:
        return error

    pending_tool_msg = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == "tool",
            Message.tool_name == f"activate_skill_{skill_id}",
        )
        .order_by(Message.created_at.desc())
        .first()
    )
    pending_tool_message_id = pending_tool_msg.id if pending_tool_msg else None

    result = SkillActivationManager.activate_skill(
        skill_id,
        conversation_id,
        db,
        current_user.id,
        source=SkillActivationManager.SOURCE_LLM_MCP,
        message_id=pending_tool_message_id,
        manual_preferred=False,
    )
    already_active = (not result.get("success")) and (
        "已激活" in (result.get("message") or "")
    )
    if result.get("success") or already_active:
        if already_active:
            result["success"] = True

        resume_assistant_message_id = None
        resume_tool_message_id = None
        refresh_root_system_prompt(conversation_id, db, current_user.id)

        if pending_tool_msg:
            resume_assistant_message_id = pending_tool_msg.parent_id
            resume_tool_message_id = pending_tool_msg.id
            pending_tool_msg.content = json.dumps(
                {
                    "type": "skill_activation_confirmed",
                    "success": True,
                    "message": result["message"],
                    "skill_name": result.get("skill_name"),
                },
                ensure_ascii=False,
            )

        db.commit()
        result["active_skills"] = get_conversation_active_skills(conv, db)
        result["resume_assistant_message_id"] = resume_assistant_message_id
        result["resume_tool_message_id"] = resume_tool_message_id

    return ApiResponse.success(data=result)


@router.post("/{conversation_id}/skills/{skill_id}/reject", response_model=ApiResponse)
def reject_skill_activation(
    conversation_id: int,
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, error = get_owned_conversation_or_error(conversation_id, current_user.id, db)
    if error:
        return error

    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    skill_name = skill.name if skill else f"Skill (id={skill_id})"
    reject_message = (
        f"用户拒绝了激活「{skill_name}」技能。"
        "本轮对话不允许再次调用该技能；如后续需要，请在下一轮再发起。"
    )

    pending_tool_msg = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == "tool",
            Message.tool_name == f"activate_skill_{skill_id}",
        )
        .order_by(Message.created_at.desc())
        .first()
    )
    resume_assistant_message_id = None
    resume_tool_message_id = None
    if pending_tool_msg:
        resume_assistant_message_id = pending_tool_msg.parent_id
        resume_tool_message_id = pending_tool_msg.id
        pending_tool_msg.content = json.dumps(
            {
                "type": "skill_activation_rejected",
                "error": True,
                "success": False,
                "message": reject_message,
                "skill_name": skill_name,
                "retry_in_current_turn_forbidden": True,
            },
            ensure_ascii=False,
        )
        db.commit()

    return ApiResponse.success(
        data={
            "success": False,
            "message": reject_message,
            "skill_name": skill_name,
            "prompt": None,
            "resume_assistant_message_id": resume_assistant_message_id,
            "resume_tool_message_id": resume_tool_message_id,
        }
    )


@router.delete("/{conversation_id}/skills/{skill_id}", response_model=ApiResponse)
def deactivate_skill(
    conversation_id: int,
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = SkillActivationManager.deactivate_skill(
        skill_id,
        conversation_id,
        db,
        current_user.id,
        source=SkillActivationManager.SOURCE_MANUAL_API,
    )
    if result.get("success"):
        refresh_root_system_prompt(conversation_id, db, current_user.id)
        db.commit()
    return ApiResponse.success(data=result)
