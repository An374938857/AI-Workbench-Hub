from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.requirement import Requirement
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionNode,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowInstanceNode,
)


def get_published_version(
    db: Session,
    workflow_definition_id: int,
    scope: str,
) -> WorkflowDefinitionVersion:
    workflow_definition = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.id == workflow_definition_id)
        .first()
    )
    if not workflow_definition:
        raise HTTPException(status_code=404, detail="流程定义不存在")
    if workflow_definition.scope != scope:
        raise HTTPException(status_code=400, detail="流程作用域不匹配")

    version = (
        db.query(WorkflowDefinitionVersion)
        .filter(
            WorkflowDefinitionVersion.workflow_definition_id == workflow_definition_id,
            WorkflowDefinitionVersion.is_published.is_(True),
        )
        .order_by(WorkflowDefinitionVersion.version_no.desc())
        .first()
    )
    if not version:
        raise HTTPException(status_code=400, detail="流程定义无已发布版本")
    return version


def create_workflow_instance(
    db: Session,
    scope_type: str,
    scope_id: int,
    workflow_definition_id: int,
    operator_id: int,
) -> WorkflowInstance:
    version = get_published_version(db, workflow_definition_id, scope_type)
    definition_nodes = (
        db.query(WorkflowDefinitionNode)
        .filter(WorkflowDefinitionNode.workflow_definition_version_id == version.id)
        .order_by(WorkflowDefinitionNode.node_order.asc())
        .all()
    )
    if not definition_nodes:
        raise HTTPException(status_code=400, detail="流程版本未配置节点")

    instance = WorkflowInstance(
        scope_type=scope_type,
        scope_id=scope_id,
        workflow_definition_id=workflow_definition_id,
        workflow_definition_version_id=version.id,
        status="IN_PROGRESS",
        started_at=datetime.now(),
        created_by=operator_id,
        updated_by=operator_id,
    )
    db.add(instance)
    db.flush()

    first_node_instance_id = None
    for idx, node in enumerate(definition_nodes):
        node_instance = WorkflowInstanceNode(
            workflow_instance_id=instance.id,
            definition_node_id=node.id,
            node_code=node.node_code,
            node_name=node.node_name,
            node_order=node.node_order,
            status="PENDING",
            updated_by=operator_id,
        )
        db.add(node_instance)
        db.flush()
        if idx == 0:
            first_node_instance_id = node_instance.id

    instance.current_node_id = first_node_instance_id
    db.flush()
    return instance


def mark_node_running_on_conversation_bind(
    node: WorkflowInstanceNode,
    operator_id: int,
) -> bool:
    """绑定会话时，若节点仍为待处理则自动推进为进行中。"""
    if node.status != "PENDING":
        return False

    node.status = "RUNNING"
    node.updated_by = operator_id
    if not node.started_at:
        node.started_at = datetime.now()
    return True


def refresh_requirement_status_from_instance(db: Session, requirement: Requirement) -> None:
    if not requirement.workflow_instance_id:
        requirement.status = "NOT_STARTED"
        return

    instance = (
        db.query(WorkflowInstance)
        .filter(WorkflowInstance.id == requirement.workflow_instance_id)
        .first()
    )
    if not instance:
        requirement.status = "NOT_STARTED"
        return

    if instance.status == "CANCELED":
        requirement.status = "CANCELED"
    elif instance.status == "COMPLETED":
        requirement.status = "COMPLETED"
    elif instance.status == "IN_PROGRESS":
        requirement.status = "IN_PROGRESS"
    else:
        requirement.status = "NOT_STARTED"
