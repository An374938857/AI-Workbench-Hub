"""搜索 API 路由"""
from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from sqlalchemy.orm import Session
from app.deps import get_current_user, get_db
from app.models.user import User
from app.models.conversation import Conversation
from app.models.skill import Skill
from app.schemas.base import ApiResponse
from app.services.search_service import search_service

router = APIRouter()

@router.get("/conversations")
async def search_conversations(
    q: Optional[str] = Query(None, min_length=1, max_length=200, description="搜索关键词（可选）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页数量"),
    skill_id: Optional[int] = Query(None, description="Skill ID筛选"),
    skill_name: Optional[str] = Query(None, description="Skill名称筛选（已废弃，使用skill_id）"),
    tags: Optional[List[str]] = Query(None, description="标签筛选"),
    date_start: Optional[str] = Query(None, description="开始日期 (ISO格式)"),
    date_end: Optional[str] = Query(None, description="结束日期 (ISO格式)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """搜索对话"""
    
    # 至少需要一个搜索条件
    if not q and not skill_id and not skill_name and not date_start:
        return ApiResponse.error(40001, "请提供至少一个搜索条件")
    
    skill_name_filter = skill_name
    if skill_id and not skill_name_filter:
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if skill:
            skill_name_filter = skill.name

    skill_filtered_conversation_ids: Optional[list[int]] = None
    if skill_id is not None:
        convs = (
            db.query(Conversation)
            .filter(Conversation.user_id == current_user.id)
            .all()
        )
        matched_ids: list[int] = []
        for conv in convs:
            ids = conv.get_active_skill_ids()
            if conv.skill_id and conv.skill_id not in ids:
                ids = [conv.skill_id] + ids
            if skill_id in ids:
                matched_ids.append(conv.id)
        skill_filtered_conversation_ids = matched_ids

    result = await search_service.search_conversations(
        user_id=current_user.id,
        query=q or "",  # 如果没有关键词，传空字符串
        page=page,
        page_size=page_size,
        skill_id=skill_id,
        skill_name=skill_name_filter,
        conversation_ids=skill_filtered_conversation_ids,
        tags=tags,
        date_start=date_start,
        date_end=date_end
    )
    
    # 补充对话详情（技能名、标签、时间）
    conv_ids = [r["conversation_id"] for r in result["results"]]
    from sqlalchemy.orm import joinedload
    conversations = db.query(Conversation).options(
        joinedload(Conversation.skill),
        joinedload(Conversation.tags)
    ).filter(Conversation.id.in_(conv_ids)).all()
    conv_map = {c.id: c for c in conversations}

    all_skill_ids: set[int] = set()
    conv_skill_ids: dict[int, list[int]] = {}
    for conv in conversations:
        ids = conv.get_active_skill_ids()
        if conv.skill_id and conv.skill_id not in ids:
            ids = [conv.skill_id] + ids
        conv_skill_ids[conv.id] = ids
        for sid in ids:
            all_skill_ids.add(sid)

    skill_rows = (
        db.query(Skill.id, Skill.name).filter(Skill.id.in_(all_skill_ids)).all()
        if all_skill_ids
        else []
    )
    skill_name_map = {row.id: row.name for row in skill_rows}

    for r in result["results"]:
        conv = conv_map.get(r["conversation_id"])
        if conv:
            active_skills = [
                {"id": sid, "name": skill_name_map[sid]}
                for sid in conv_skill_ids.get(conv.id, [])
                if sid in skill_name_map
            ]
            r["active_skills"] = active_skills
            if active_skills:
                first = active_skills[0]["name"]
                r["skill_name"] = first if len(active_skills) == 1 else f"{first} +{len(active_skills) - 1}"
            else:
                r["skill_name"] = "自由对话"
            r["tags"] = [{"id": t.id, "name": t.name, "color": t.color} for t in conv.tags]
            r["updated_at"] = conv.updated_at.isoformat()

    return ApiResponse.success(data={
        "total": result["total"],
        "results": result["results"],
        "page": page,
        "page_size": page_size
    })
