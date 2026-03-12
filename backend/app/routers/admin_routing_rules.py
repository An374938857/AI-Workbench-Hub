from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.models.routing_rule import RoutingRule
from app.models.user import User
from app.schemas.base import ApiResponse

router = APIRouter()


class RoutingRuleBody(BaseModel):
    intent_category: str
    display_name: str
    keywords: list[str]
    preferred_tags: list[str]
    preferred_model: Optional[str] = None
    priority: int = 0
    is_enabled: bool = True


def _rule_to_dict(r: RoutingRule) -> dict:
    return {
        "id": r.id,
        "intent_category": r.intent_category,
        "display_name": r.display_name,
        "keywords": r.keywords,
        "preferred_tags": r.preferred_tags,
        "preferred_model": r.preferred_model,
        "priority": r.priority,
        "is_enabled": r.is_enabled,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("")
def list_rules(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    rules = db.query(RoutingRule).order_by(RoutingRule.priority.desc(), RoutingRule.id).all()
    return ApiResponse.success(data={"items": [_rule_to_dict(r) for r in rules]})


@router.post("")
def create_rule(
    body: RoutingRuleBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    rule = RoutingRule(**body.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return ApiResponse.success(data=_rule_to_dict(rule), message="创建成功")


@router.put("/{rule_id}")
def update_rule(
    rule_id: int,
    body: RoutingRuleBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    rule = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    if not rule:
        return ApiResponse.error(40401, "规则不存在")
    for k, v in body.model_dump().items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return ApiResponse.success(data=_rule_to_dict(rule), message="更新成功")


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    rule = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    if not rule:
        return ApiResponse.error(40401, "规则不存在")
    db.delete(rule)
    db.commit()
    return ApiResponse.success(message="删除成功")
