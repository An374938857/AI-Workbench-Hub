from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_role
from app.models.requirement import Requirement
from app.models.conversation import Conversation
from app.models.skill import Skill
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinitionNode,
    WorkflowInstance,
    WorkflowInstanceNode,
    WorkflowInstanceNodeOutput,
    WorkflowNodeConversation,
    WorkflowTransitionLog,
)
from app.routers.conversations_shared import build_skill_display_name
from app.schemas.base import ApiResponse
from app.schemas.workflow_delivery import (
    WorkflowInstanceCreate,
    WorkflowNodeAdvance,
    WorkflowNodeBindConversations,
    WorkflowNodeOutputCreate,
)
from app.services.workflow_instance_service import (
    create_workflow_instance,
    mark_node_running_on_conversation_bind,
    refresh_requirement_status_from_instance,
)

router = APIRouter()


def _get_instance_node_or_error(
    db: Session,
    instance_id: int,
    node_id: int,
) -> tuple[WorkflowInstanceNode | None, ApiResponse | None]:
    node = (
        db.query(WorkflowInstanceNode)
        .filter(
            WorkflowInstanceNode.id == node_id,
            WorkflowInstanceNode.workflow_instance_id == instance_id,
        )
        .first()
    )
    if not node:
        return None, ApiResponse.error(40401, "节点不存在")
    return node, None


def _next_output_version_no(db: Session, node_id: int, deliverable_type: str) -> int:
    max_version = (
        db.query(func.max(WorkflowInstanceNodeOutput.version_no))
        .filter(
            WorkflowInstanceNodeOutput.workflow_instance_node_id == node_id,
            WorkflowInstanceNodeOutput.deliverable_type == deliverable_type,
        )
        .scalar()
    )
    return int(max_version or 0) + 1


def _output_to_dict(output: WorkflowInstanceNodeOutput) -> dict:
    return {
        "id": output.id,
        "workflow_instance_node_id": output.workflow_instance_node_id,
        "conversation_id": output.conversation_id,
        "output_kind": output.output_kind,
        "deliverable_type": output.deliverable_type,
        "version_no": output.version_no,
        "title": output.title,
        "summary": output.summary,
        "content_type": output.content_type,
        "content_ref": output.content_ref,
        "is_current": output.is_current,
        "status": output.status,
        "created_at": output.created_at.isoformat() if output.created_at else None,
    }


def _instance_to_dict(instance: WorkflowInstance) -> dict:
    return {
        "id": instance.id,
        "scope_type": instance.scope_type,
        "scope_id": instance.scope_id,
        "workflow_definition_id": instance.workflow_definition_id,
        "workflow_definition_version_id": instance.workflow_definition_version_id,
        "status": instance.status,
        "current_node_id": instance.current_node_id,
        "nodes": [
            {
                "id": node.id,
                "node_code": node.node_code,
                "node_name": node.node_name,
                "node_order": node.node_order,
                "status": node.status,
                "conversation_count": len(node.conversations),
            }
            for node in sorted(instance.nodes, key=lambda item: item.node_order)
        ],
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "updated_at": instance.updated_at.isoformat() if instance.updated_at else None,
    }


@router.post("")
def create_instance(
    body: WorkflowInstanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    instance = create_workflow_instance(
        db=db,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        workflow_definition_id=body.workflow_definition_id,
        operator_id=current_user.id,
    )

    if body.scope_type == "REQUIREMENT":
        requirement = db.query(Requirement).filter(Requirement.id == body.scope_id).first()
        if requirement:
            requirement.workflow_definition_id = body.workflow_definition_id
            requirement.workflow_instance_id = instance.id
            requirement.updated_by = current_user.id
            refresh_requirement_status_from_instance(db, requirement)

    db.commit()
    db.refresh(instance)
    return ApiResponse.success(data=_instance_to_dict(instance))


@router.get("/{instance_id}")
def get_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    instance = db.query(WorkflowInstance).filter(WorkflowInstance.id == instance_id).first()
    if not instance:
        return ApiResponse.error(40401, "流程实例不存在")
    return ApiResponse.success(data=_instance_to_dict(instance))


@router.post("/{instance_id}/nodes/{node_id}/bind-conversations")
def bind_node_conversations(
    instance_id: int,
    node_id: int,
    body: WorkflowNodeBindConversations,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    node, error = _get_instance_node_or_error(db, instance_id, node_id)
    if error:
        return error

    existing_conversations = (
        db.query(Conversation)
        .filter(Conversation.id.in_(body.conversation_ids))
        .all()
    )
    conversation_map = {item.id: item for item in existing_conversations}
    missing_ids = [item for item in body.conversation_ids if item not in conversation_map]
    if missing_ids:
        return ApiResponse.error(40401, f"会话不存在: {','.join(str(item) for item in missing_ids)}")

    if current_user.role != "admin":
        unauthorized_ids = [
            conv.id for conv in conversation_map.values() if conv.user_id != current_user.id
        ]
        if unauthorized_ids:
            return ApiResponse.error(40301, f"无权限绑定会话: {','.join(str(item) for item in unauthorized_ids)}")

    existing = (
        db.query(WorkflowNodeConversation)
        .filter(WorkflowNodeConversation.conversation_id.in_(body.conversation_ids))
        .all()
    )
    bound_map = {item.conversation_id: item for item in existing}
    for conversation_id in body.conversation_ids:
        bound = bound_map.get(conversation_id)
        if bound and bound.workflow_instance_node_id != node_id:
            return ApiResponse.error(40901, f"会话 {conversation_id} 已绑定其他节点")
        if bound and bound.workflow_instance_node_id == node_id:
            continue
        db.add(
            WorkflowNodeConversation(
                workflow_instance_node_id=node_id,
                conversation_id=conversation_id,
                binding_type=body.binding_type,
                created_by=current_user.id,
            )
        )

    mark_node_running_on_conversation_bind(node, current_user.id)

    db.commit()
    return ApiResponse.success(message="会话绑定成功")


@router.get("/{instance_id}/nodes/{node_id}/conversations")
def list_node_conversations(
    instance_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    node, error = _get_instance_node_or_error(db, instance_id, node_id)
    if error:
        return error

    definition_node = (
        db.query(WorkflowDefinitionNode)
        .filter(WorkflowDefinitionNode.id == node.definition_node_id)
        .first()
    )
    skill_name = None
    if definition_node and definition_node.skill_id:
        skill = db.query(Skill).filter(Skill.id == definition_node.skill_id).first()
        if skill:
            skill_name = skill.name

    bindings = (
        db.query(WorkflowNodeConversation)
        .filter(WorkflowNodeConversation.workflow_instance_node_id == node_id)
        .order_by(WorkflowNodeConversation.id.desc())
        .all()
    )
    conversation_ids = [item.conversation_id for item in bindings]
    conversations = (
        db.query(Conversation)
        .filter(Conversation.id.in_(conversation_ids))
        .all()
        if conversation_ids
        else []
    )
    conversation_map = {item.id: item for item in conversations}

    active_skill_ids: set[int] = set()
    conversation_skill_ids: dict[int, list[int]] = {}
    for conv in conversations:
        ids = conv.get_active_skill_ids()
        if conv.skill_id and conv.skill_id not in ids:
            ids = [conv.skill_id] + ids
        conversation_skill_ids[conv.id] = ids
        active_skill_ids.update(ids)

    skill_map = {
        row.id: row.name
        for row in db.query(Skill.id, Skill.name).filter(Skill.id.in_(active_skill_ids)).all()
    } if active_skill_ids else {}

    payload = []
    for binding in bindings:
        conv = conversation_map.get(binding.conversation_id)
        if not conv:
            continue
        active_skills = [
            {"id": sid, "name": skill_map[sid]}
            for sid in conversation_skill_ids.get(conv.id, [])
            if sid in skill_map
        ]
        can_view = current_user.role == "admin" or conv.user_id == current_user.id
        payload.append(
            {
                "binding_id": binding.id,
                "conversation_id": conv.id,
                "title": conv.title or "新对话",
                "binding_type": binding.binding_type,
                "created_at": binding.created_at.isoformat() if binding.created_at else None,
                "skill_name": build_skill_display_name(active_skills),
                "active_skills": active_skills,
                "can_view": can_view,
            }
        )

    return ApiResponse.success(
        data={
            "node": {
                "id": node.id,
                "node_code": node.node_code,
                "node_name": node.node_name,
                "skill_id": definition_node.skill_id if definition_node else None,
                "skill_name": skill_name,
            },
            "items": payload,
        }
    )


@router.delete("/{instance_id}/nodes/{node_id}/conversations/{conversation_id}")
def unbind_node_conversation(
    instance_id: int,
    node_id: int,
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    _node, error = _get_instance_node_or_error(db, instance_id, node_id)
    if error:
        return error

    binding = (
        db.query(WorkflowNodeConversation)
        .filter(
            WorkflowNodeConversation.workflow_instance_node_id == node_id,
            WorkflowNodeConversation.conversation_id == conversation_id,
        )
        .first()
    )
    if not binding:
        return ApiResponse.error(40401, "会话未绑定到该节点")

    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv and current_user.role != "admin" and conv.user_id != current_user.id:
        return ApiResponse.error(40301, "无权限解绑该会话")

    db.delete(binding)
    db.commit()
    return ApiResponse.success(message="会话解绑成功")


@router.post("/{instance_id}/nodes/{node_id}/advance")
def advance_node(
    instance_id: int,
    node_id: int,
    body: WorkflowNodeAdvance,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    instance = db.query(WorkflowInstance).filter(WorkflowInstance.id == instance_id).first()
    if not instance:
        return ApiResponse.error(40401, "流程实例不存在")
    if instance.status == "CANCELED":
        return ApiResponse.error(40901, "实例已取消，不能推进")

    node, error = _get_instance_node_or_error(db, instance_id, node_id)
    if error:
        return error

    if body.to_status == "SKIPPED" and not body.skip_reason:
        return ApiResponse.error(40001, "跳过节点必须填写 skip_reason")

    from_status = node.status
    node.status = body.to_status
    node.manual_note = body.note
    node.skip_reason = body.skip_reason
    node.updated_by = current_user.id

    if body.to_status == "RUNNING" and not node.started_at:
        node.started_at = datetime.now()
    if body.to_status in {"SUCCEEDED", "FAILED", "SKIPPED", "CANCELED"}:
        node.ended_at = datetime.now()

    if body.to_status in {"SUCCEEDED", "SKIPPED"}:
        next_node = (
            db.query(WorkflowInstanceNode)
            .filter(
                WorkflowInstanceNode.workflow_instance_id == instance_id,
                WorkflowInstanceNode.node_order > node.node_order,
            )
            .order_by(WorkflowInstanceNode.node_order.asc())
            .first()
        )
        if next_node:
            if next_node.status in {"BLOCKED", "NOT_STARTED"}:
                next_node.status = "PENDING"
                next_node.updated_by = current_user.id
            instance.current_node_id = next_node.id
            instance.status = "IN_PROGRESS"
        else:
            instance.current_node_id = None
            instance.status = "COMPLETED"
            instance.completed_at = datetime.now()
    else:
        if body.to_status == "RUNNING":
            instance.status = "IN_PROGRESS"
            instance.current_node_id = node.id

    instance.updated_by = current_user.id

    db.add(
        WorkflowTransitionLog(
            workflow_instance_id=instance_id,
            workflow_instance_node_id=node_id,
            action="SKIP" if body.to_status == "SKIPPED" else "ADVANCE",
            from_status=from_status,
            to_status=body.to_status,
            is_overridden=False,
            operator_user_id=current_user.id,
            note=body.note,
        )
    )

    if instance.scope_type == "REQUIREMENT":
        requirement = db.query(Requirement).filter(Requirement.id == instance.scope_id).first()
        if requirement:
            refresh_requirement_status_from_instance(db, requirement)
            requirement.updated_by = current_user.id

    db.commit()
    db.refresh(instance)
    return ApiResponse.success(data=_instance_to_dict(instance))


@router.post("/{instance_id}/nodes/{node_id}/retry-conversation")
def retry_conversation(
    instance_id: int,
    node_id: int,
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    node, error = _get_instance_node_or_error(db, instance_id, node_id)
    if error:
        return error

    binding = (
        db.query(WorkflowNodeConversation)
        .filter(
            WorkflowNodeConversation.workflow_instance_node_id == node_id,
            WorkflowNodeConversation.conversation_id == conversation_id,
        )
        .first()
    )
    if not binding:
        return ApiResponse.error(40401, "会话未绑定到该节点")

    node.status = "PENDING"
    node.manual_note = f"会话 {conversation_id} 触发重试"
    node.updated_by = current_user.id

    db.add(
        WorkflowTransitionLog(
            workflow_instance_id=instance_id,
            workflow_instance_node_id=node_id,
            action="RETRY",
            from_status="FAILED",
            to_status="PENDING",
            is_overridden=False,
            operator_user_id=current_user.id,
            note=f"retry conversation: {conversation_id}",
        )
    )
    db.commit()
    return ApiResponse.success(message="会话重试已触发")


@router.get("/{instance_id}/nodes/{node_id}/outputs")
def list_node_outputs(
    instance_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    _node, error = _get_instance_node_or_error(db, instance_id, node_id)
    if error:
        return error

    outputs = (
        db.query(WorkflowInstanceNodeOutput)
        .filter(WorkflowInstanceNodeOutput.workflow_instance_node_id == node_id)
        .order_by(
            WorkflowInstanceNodeOutput.deliverable_type.asc(),
            WorkflowInstanceNodeOutput.version_no.desc(),
            WorkflowInstanceNodeOutput.id.desc(),
        )
        .all()
    )
    return ApiResponse.success(data=[_output_to_dict(output) for output in outputs])


@router.post("/{instance_id}/nodes/{node_id}/outputs")
def create_node_output(
    instance_id: int,
    node_id: int,
    body: WorkflowNodeOutputCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    _node, error = _get_instance_node_or_error(db, instance_id, node_id)
    if error:
        return error

    next_version = _next_output_version_no(db, node_id, body.deliverable_type)
    db.query(WorkflowInstanceNodeOutput).filter(
        WorkflowInstanceNodeOutput.workflow_instance_node_id == node_id,
        WorkflowInstanceNodeOutput.deliverable_type == body.deliverable_type,
        WorkflowInstanceNodeOutput.is_current.is_(True),
    ).update({"is_current": False}, synchronize_session=False)

    output = WorkflowInstanceNodeOutput(
        workflow_instance_node_id=node_id,
        conversation_id=body.conversation_id,
        output_kind=body.output_kind,
        deliverable_type=body.deliverable_type,
        version_no=next_version,
        title=body.title,
        summary=body.summary,
        content_type=body.content_type,
        content_ref=body.content_ref,
        is_current=True,
        status="ACTIVE",
        created_by=current_user.id,
    )
    db.add(output)
    db.commit()
    db.refresh(output)
    return ApiResponse.success(data=_output_to_dict(output))


@router.post("/{instance_id}/nodes/{node_id}/outputs/{output_id}/set-current")
def set_current_output(
    instance_id: int,
    node_id: int,
    output_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("user", "admin")),
):
    _node, error = _get_instance_node_or_error(db, instance_id, node_id)
    if error:
        return error

    output = (
        db.query(WorkflowInstanceNodeOutput)
        .filter(
            WorkflowInstanceNodeOutput.id == output_id,
            WorkflowInstanceNodeOutput.workflow_instance_node_id == node_id,
        )
        .first()
    )
    if not output:
        return ApiResponse.error(40401, "交付物版本不存在")

    db.query(WorkflowInstanceNodeOutput).filter(
        WorkflowInstanceNodeOutput.workflow_instance_node_id == node_id,
        WorkflowInstanceNodeOutput.deliverable_type == output.deliverable_type,
        WorkflowInstanceNodeOutput.is_current.is_(True),
    ).update({"is_current": False}, synchronize_session=False)

    output.is_current = True
    db.commit()
    db.refresh(output)
    return ApiResponse.success(data=_output_to_dict(output), message="当前版本切换成功")


@router.post("/{instance_id}/rollback-recompute")
def rollback_recompute(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    instance = db.query(WorkflowInstance).filter(WorkflowInstance.id == instance_id).first()
    if not instance:
        return ApiResponse.error(40401, "流程实例不存在")

    nodes = (
        db.query(WorkflowInstanceNode)
        .filter(WorkflowInstanceNode.workflow_instance_id == instance_id)
        .order_by(WorkflowInstanceNode.node_order.asc())
        .all()
    )
    reset_count = 0
    for node in nodes:
        if node.status == "SUCCEEDED":
            node.status = "PENDING"
            node.is_affected = True
            node.updated_by = current_user.id
            reset_count += 1

    if reset_count > 0:
        instance.status = "IN_PROGRESS"
        instance.completed_at = None
        first_pending = next((item for item in nodes if item.status == "PENDING"), None)
        instance.current_node_id = first_pending.id if first_pending else None
    instance.updated_by = current_user.id

    db.add(
        WorkflowTransitionLog(
            workflow_instance_id=instance_id,
            workflow_instance_node_id=instance.current_node_id,
            action="OVERRIDE",
            from_status="COMPLETED",
            to_status=instance.status,
            is_overridden=True,
            operator_user_id=current_user.id,
            note=f"rollback recompute affected_nodes={reset_count}",
        )
    )

    if instance.scope_type == "REQUIREMENT":
        requirement = db.query(Requirement).filter(Requirement.id == instance.scope_id).first()
        if requirement:
            refresh_requirement_status_from_instance(db, requirement)
            requirement.updated_by = current_user.id

    db.commit()
    return ApiResponse.success(data={"affected_nodes": reset_count}, message="回退重算完成")


@router.post("/{instance_id}/cancel")
def cancel_instance(
    instance_id: int,
    note: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    instance = db.query(WorkflowInstance).filter(WorkflowInstance.id == instance_id).first()
    if not instance:
        return ApiResponse.error(40401, "流程实例不存在")

    nodes = db.query(WorkflowInstanceNode).filter(WorkflowInstanceNode.workflow_instance_id == instance_id).all()
    for node in nodes:
        if node.status == "RUNNING":
            node.status = "CANCELED"
            node.ended_at = datetime.now()
            node.updated_by = current_user.id

    instance.status = "CANCELED"
    instance.canceled_at = datetime.now()
    instance.updated_by = current_user.id
    db.add(
        WorkflowTransitionLog(
            workflow_instance_id=instance_id,
            workflow_instance_node_id=instance.current_node_id,
            action="OVERRIDE",
            from_status="IN_PROGRESS",
            to_status="CANCELED",
            is_overridden=True,
            operator_user_id=current_user.id,
            note=note,
        )
    )
    if instance.scope_type == "REQUIREMENT":
        requirement = db.query(Requirement).filter(Requirement.id == instance.scope_id).first()
        if requirement:
            refresh_requirement_status_from_instance(db, requirement)
            requirement.updated_by = current_user.id

    db.commit()
    return ApiResponse.success(message="实例已取消")


@router.post("/{instance_id}/resume")
def resume_instance(
    instance_id: int,
    note: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    instance = db.query(WorkflowInstance).filter(WorkflowInstance.id == instance_id).first()
    if not instance:
        return ApiResponse.error(40401, "流程实例不存在")
    if instance.status != "CANCELED":
        return ApiResponse.error(40901, "仅 CANCELED 实例可恢复")

    instance.status = "IN_PROGRESS"
    instance.canceled_at = None
    instance.updated_by = current_user.id

    next_node = (
        db.query(WorkflowInstanceNode)
        .filter(
            WorkflowInstanceNode.workflow_instance_id == instance_id,
            WorkflowInstanceNode.status.in_(["PENDING", "BLOCKED", "FAILED", "CANCELED"]),
        )
        .order_by(WorkflowInstanceNode.node_order.asc())
        .first()
    )
    if next_node:
        if next_node.status == "CANCELED":
            next_node.status = "PENDING"
            next_node.updated_by = current_user.id
        instance.current_node_id = next_node.id

    db.add(
        WorkflowTransitionLog(
            workflow_instance_id=instance_id,
            workflow_instance_node_id=instance.current_node_id,
            action="OVERRIDE",
            from_status="CANCELED",
            to_status="IN_PROGRESS",
            is_overridden=True,
            operator_user_id=current_user.id,
            note=note,
        )
    )
    if instance.scope_type == "REQUIREMENT":
        requirement = db.query(Requirement).filter(Requirement.id == instance.scope_id).first()
        if requirement:
            refresh_requirement_status_from_instance(db, requirement)
            requirement.updated_by = current_user.id

    db.commit()
    db.refresh(instance)
    return ApiResponse.success(data=_instance_to_dict(instance), message="实例已恢复")
