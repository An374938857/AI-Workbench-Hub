from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.models.conversation import Conversation
from app.models.feedback import Feedback
from app.models.mcp import Mcp
from app.models.mcp_call_log import McpCallLog
from app.models.skill import Skill
from app.models.usage_log import UsageLog
from app.models.user import User
from app.schemas.base import ApiResponse

router = APIRouter()


def _parse_dates(start_date: Optional[str], end_date: Optional[str]):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.now() - timedelta(days=30)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59) if end_date else datetime.now()
    except ValueError:
        start = datetime.now() - timedelta(days=30)
        end = datetime.now()
    return start, end


@router.get("/overview")
def get_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    total_users = db.query(func.count(User.id)).scalar()

    seven_days_ago = datetime.now() - timedelta(days=7)
    active_users = (
        db.query(func.count(func.distinct(Conversation.user_id)))
        .filter(Conversation.updated_at >= seven_days_ago, Conversation.is_test == False)
        .scalar()
    )

    total_conversations = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.is_test == False)
        .scalar()
    )

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_conversations = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.created_at >= today_start, Conversation.is_test == False)
        .scalar()
    )

    total_tokens = db.query(func.coalesce(func.sum(UsageLog.total_tokens), 0)).scalar()

    return ApiResponse.success(data={
        "total_users": total_users,
        "active_users_7d": active_users,
        "total_conversations": total_conversations,
        "today_conversations": today_conversations,
        "total_tokens": total_tokens,
    })


@router.get("/skills")
def get_skill_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    start, end = _parse_dates(start_date, end_date)

    rows = (
        db.query(
            Skill.id,
            Skill.name,
            func.count(UsageLog.id).label("call_count"),
            func.coalesce(
                func.sum(case((UsageLog.is_success == True, 1), else_=0)) * 1.0 / func.count(UsageLog.id),
                0,
            ).label("success_rate"),
            func.coalesce(func.sum(UsageLog.total_tokens), 0).label("total_tokens"),
            func.max(UsageLog.created_at).label("last_used_at"),
        )
        .outerjoin(UsageLog, (UsageLog.skill_id == Skill.id) & (UsageLog.created_at.between(start, end)))
        .group_by(Skill.id, Skill.name)
        .order_by(func.count(UsageLog.id).desc())
        .all()
    )

    # 查询平均评分
    rating_map = dict(
        db.query(Feedback.skill_id, func.avg(Feedback.rating))
        .group_by(Feedback.skill_id)
        .all()
    )

    return ApiResponse.success(data=[
        {
            "skill_id": r.id,
            "skill_name": r.name,
            "call_count": r.call_count,
            "success_rate": round(float(r.success_rate), 2),
            "avg_rating": round(float(rating_map.get(r.id, 0)), 1),
            "total_tokens": r.total_tokens,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
        }
        for r in rows
    ])


@router.get("/tokens")
def get_token_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = Query("skill", pattern="^(provider|skill|user|model)$"),
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    start, end = _parse_dates(start_date, end_date)
    base = db.query(UsageLog).filter(UsageLog.created_at.between(start, end))

    if group_by == "skill":
        rows = (
            base.with_entities(
                Skill.name.label("label"),
                func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).label("total_tokens"),
            )
            .outerjoin(Skill, Skill.id == UsageLog.skill_id)
            .group_by(Skill.name)
            .order_by(func.sum(UsageLog.total_tokens).desc())
            .limit(20)
            .all()
        )
    elif group_by == "user":
        rows = (
            base.with_entities(
                User.display_name.label("label"),
                func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).label("total_tokens"),
            )
            .join(User, User.id == UsageLog.user_id)
            .group_by(User.display_name)
            .order_by(func.sum(UsageLog.total_tokens).desc())
            .limit(10)
            .all()
        )
    elif group_by == "model":
        from app.models.model_provider import ModelProvider
        rows = (
            base.with_entities(
                ModelProvider.provider_name.label("provider_name"),
                UsageLog.model_name.label("model_name"),
                func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).label("total_tokens"),
            )
            .join(ModelProvider, ModelProvider.id == UsageLog.provider_id)
            .group_by(ModelProvider.provider_name, UsageLog.model_name)
            .order_by(func.sum(UsageLog.total_tokens).desc())
            .limit(20)
            .all()
        )
    else:
        from app.models.model_provider import ModelProvider
        rows = (
            base.with_entities(
                ModelProvider.provider_name.label("label"),
                func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).label("total_tokens"),
            )
            .join(ModelProvider, ModelProvider.id == UsageLog.provider_id)
            .group_by(ModelProvider.provider_name)
            .order_by(func.sum(UsageLog.total_tokens).desc())
            .all()
        )

    if group_by == "model":
        data = [
            {
                "label": f"{(r.provider_name or '未知提供商')} / {(r.model_name or '未知模型')}",
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens": r.total_tokens,
            }
            for r in rows
        ]
    else:
        data = [
            {
                "label": r.label or "自由对话",
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens": r.total_tokens,
            }
            for r in rows
        ]

    return ApiResponse.success(data=data)


@router.get("/trends")
def get_trends(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    metric: str = Query("conversations", pattern="^(conversations|tokens|tool_calls)$"),
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    start, end = _parse_dates(start_date, end_date)

    if metric == "conversations":
        rows = (
            db.query(
                func.date(Conversation.created_at).label("date"),
                func.count(Conversation.id).label("value"),
            )
            .filter(Conversation.created_at.between(start, end), Conversation.is_test == False)
            .group_by(func.date(Conversation.created_at))
            .order_by(func.date(Conversation.created_at))
            .all()
        )
    elif metric == "tokens":
        rows = (
            db.query(
                func.date(UsageLog.created_at).label("date"),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).label("value"),
            )
            .filter(UsageLog.created_at.between(start, end))
            .group_by(func.date(UsageLog.created_at))
            .order_by(func.date(UsageLog.created_at))
            .all()
        )
    else:
        rows = (
            db.query(
                func.date(McpCallLog.created_at).label("date"),
                func.count(McpCallLog.id).label("value"),
            )
            .filter(McpCallLog.created_at.between(start, end))
            .group_by(func.date(McpCallLog.created_at))
            .order_by(func.date(McpCallLog.created_at))
            .all()
        )

    return ApiResponse.success(data=[
        {"date": str(r.date), "value": r.value}
        for r in rows
    ])


# ────── MCP 看板接口（新增）──────

@router.get("/mcp-overview")
def get_mcp_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    start, end = _parse_dates(start_date, end_date)

    total_mcps = db.query(func.count(Mcp.id)).scalar()
    enabled_mcps = db.query(func.count(Mcp.id)).filter(Mcp.is_enabled == True).scalar()

    base = db.query(McpCallLog).filter(McpCallLog.created_at.between(start, end))
    total_tool_calls = base.count()

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_tool_calls = (
        db.query(func.count(McpCallLog.id))
        .filter(McpCallLog.created_at >= today_start)
        .scalar()
    )

    success_count = base.filter(McpCallLog.is_success == True).count()
    success_rate = round(success_count / total_tool_calls, 2) if total_tool_calls > 0 else 0

    avg_rt = base.with_entities(func.avg(McpCallLog.response_time_ms)).scalar()

    return ApiResponse.success(data={
        "total_mcps": total_mcps,
        "enabled_mcps": enabled_mcps,
        "total_tool_calls": total_tool_calls,
        "today_tool_calls": today_tool_calls,
        "tool_call_success_rate": success_rate,
        "avg_response_time_ms": round(float(avg_rt or 0), 0),
    })


@router.get("/mcp-stats")
def get_mcp_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    start, end = _parse_dates(start_date, end_date)

    rows = (
        db.query(
            Mcp.id,
            Mcp.name,
            func.count(McpCallLog.id).label("call_count"),
            func.coalesce(
                func.sum(case((McpCallLog.is_success == True, 1), else_=0)) * 1.0
                / func.nullif(func.count(McpCallLog.id), 0),
                0,
            ).label("success_rate"),
            func.coalesce(func.avg(McpCallLog.response_time_ms), 0).label("avg_response_time_ms"),
            func.max(McpCallLog.created_at).label("last_called_at"),
        )
        .outerjoin(McpCallLog, (McpCallLog.mcp_id == Mcp.id) & (McpCallLog.created_at.between(start, end)))
        .group_by(Mcp.id, Mcp.name)
        .order_by(func.count(McpCallLog.id).desc())
        .all()
    )

    return ApiResponse.success(data=[
        {
            "mcp_id": r.id,
            "mcp_name": r.name,
            "call_count": r.call_count,
            "success_rate": round(float(r.success_rate), 2),
            "avg_response_time_ms": round(float(r.avg_response_time_ms), 0),
            "last_called_at": r.last_called_at.isoformat() if r.last_called_at else None,
        }
        for r in rows
    ])


@router.get("/tool-ranking")
def get_tool_ranking(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    start, end = _parse_dates(start_date, end_date)

    rows = (
        db.query(
            McpCallLog.tool_name,
            Mcp.name.label("mcp_name"),
            func.count(McpCallLog.id).label("call_count"),
        )
        .join(Mcp, Mcp.id == McpCallLog.mcp_id)
        .filter(McpCallLog.created_at.between(start, end))
        .group_by(McpCallLog.tool_name, Mcp.name)
        .order_by(func.count(McpCallLog.id).desc())
        .limit(limit)
        .all()
    )

    return ApiResponse.success(data=[
        {
            "tool_name": r.tool_name,
            "mcp_name": r.mcp_name,
            "call_count": r.call_count,
        }
        for r in rows
    ])
