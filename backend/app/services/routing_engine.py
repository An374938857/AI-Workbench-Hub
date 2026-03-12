"""智能路由引擎：根据用户消息意图自动选择最佳模型"""
from typing import Optional
from sqlalchemy.orm import Session

from app.models.routing_rule import RoutingRule
from app.models.model_provider import ModelItem, ModelProvider


def _classify_intent(content: str, db: Session) -> Optional[RoutingRule]:
    """关键词规则匹配意图，返回最高优先级匹配的规则"""
    rules = (
        db.query(RoutingRule)
        .filter(RoutingRule.is_enabled == True)
        .order_by(RoutingRule.priority.desc())
        .all()
    )
    text = content.lower()
    best_rule = None
    best_score = 0

    for rule in rules:
        score = 0
        for kw in (rule.keywords or []):
            if kw.lower() in text:
                score += len(kw)
        if score > best_score:
            best_score = score
            best_rule = rule

    return best_rule if best_score > 0 else None


def _route_model(
    rule: RoutingRule, db: Session
) -> Optional[tuple[int, str, str]]:
    """
    根据路由规则选择模型。
    返回 (provider_id, model_name, reason) 或 None。
    AC-7: 首选不可用时 fallback 到同标签次选。
    """
    # 1. 首选模型
    if rule.preferred_model:
        parts = rule.preferred_model.split(":")
        if len(parts) == 2:
            pid, mname = int(parts[0]), parts[1]
            item = (
                db.query(ModelItem)
                .join(ModelProvider)
                .filter(
                    ModelItem.provider_id == pid,
                    ModelItem.model_name == mname,
                    ModelItem.is_enabled == True,
                    ModelProvider.is_enabled == True,
                )
                .first()
            )
            if item:
                return item.provider_id, item.model_name, rule.display_name

    # 2. 按首选标签匹配
    preferred_tags = rule.preferred_tags or []
    if preferred_tags:
        candidates = (
            db.query(ModelItem)
            .join(ModelProvider)
            .filter(ModelItem.is_enabled == True, ModelProvider.is_enabled == True)
            .all()
        )
        # 按标签重叠数排序
        scored = []
        for m in candidates:
            tags = set(m.capability_tags or [])
            overlap = len(tags & set(preferred_tags))
            if overlap > 0:
                scored.append((overlap, m))
        scored.sort(key=lambda x: -x[0])
        if scored:
            m = scored[0][1]
            return m.provider_id, m.model_name, rule.display_name

    return None


def route_for_message(
    content: str, db: Session
) -> Optional[tuple[int, str, str]]:
    """
    对外入口：对消息做意图分类 + 模型路由。
    返回 (provider_id, model_name, reason_display_name) 或 None。
    """
    rule = _classify_intent(content, db)
    if not rule:
        return None
    return _route_model(rule, db)
