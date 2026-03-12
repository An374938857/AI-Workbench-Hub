from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.base import ApiResponse
from app.services.prompt_combiner import PromptCombiner
from app.services.skill_activation_manager import SkillActivationManager
from app.utils.token_counter import count_tokens


def build_skill_display_name(active_skills: list[dict]) -> str:
    if not active_skills:
        return "自由对话"
    first_name = active_skills[0]["name"]
    if len(active_skills) == 1:
        return first_name
    return f"{first_name} +{len(active_skills) - 1}"


def get_conversation_active_skills(conv: Conversation, db: Session) -> list[dict]:
    skills = SkillActivationManager.get_active_skills(conv.id, db, conv.user_id)
    return [{"id": item["id"], "name": item["name"]} for item in skills]


def serialize_conversation_skill_info(conv: Conversation, db: Session) -> dict:
    active_skills = get_conversation_active_skills(conv, db)
    return {
        "active_skills": active_skills,
        "skill_name": build_skill_display_name(active_skills),
    }


def refresh_root_system_prompt(
    conversation_id: int, db: Session, user_id: int
) -> None:
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return

    combined_prompt = PromptCombiner.combine_prompts(db, conv, user_id)
    combined_prompt = PromptCombiner.truncate_if_needed(combined_prompt)

    root_system_msg = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == "system",
            Message.parent_id.is_(None),
            Message.is_active == True,
        )
        .order_by(Message.created_at.asc())
        .first()
    )

    if combined_prompt:
        if root_system_msg:
            root_system_msg.content = combined_prompt
            root_system_msg.token_count = count_tokens(combined_prompt)
        else:
            db.add(
                Message(
                    conversation_id=conversation_id,
                    role="system",
                    content=combined_prompt,
                    token_count=count_tokens(combined_prompt),
                    parent_id=None,
                    branch_index=0,
                    is_active=True,
                )
            )


def get_owned_conversation_or_error(
    conversation_id: int,
    user_id: int,
    db: Session,
    error_code: int = 40401,
    error_message: str = "对话不存在",
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )
    if not conv:
        return None, ApiResponse.error(error_code, error_message)
    return conv, None
