from datetime import datetime

from sqlalchemy.orm import Session

from app.models.workflow import (
    WorkflowDefinitionNode,
    WorkflowInstance,
    WorkflowInstanceNode,
    WorkflowTransitionLog,
)


def switch_instances_to_version(
    db: Session,
    workflow_definition_id: int,
    target_version_id: int,
    operator_user_id: int,
) -> int:
    target_nodes = (
        db.query(WorkflowDefinitionNode)
        .filter(WorkflowDefinitionNode.workflow_definition_version_id == target_version_id)
        .order_by(WorkflowDefinitionNode.node_order.asc())
        .all()
    )
    target_node_map = {node.node_code: node for node in target_nodes}

    instances = (
        db.query(WorkflowInstance)
        .filter(WorkflowInstance.workflow_definition_id == workflow_definition_id)
        .all()
    )

    switched = 0
    for instance in instances:
        old_version_id = instance.workflow_definition_version_id
        if old_version_id == target_version_id:
            continue

        old_nodes = (
            db.query(WorkflowInstanceNode)
            .filter(WorkflowInstanceNode.workflow_instance_id == instance.id)
            .all()
        )
        old_node_map = {node.node_code: node for node in old_nodes}

        for code, def_node in target_node_map.items():
            if code not in old_node_map:
                db.add(
                    WorkflowInstanceNode(
                        workflow_instance_id=instance.id,
                        definition_node_id=def_node.id,
                        node_code=def_node.node_code,
                        node_name=def_node.node_name,
                        node_order=def_node.node_order,
                        status="BLOCKED",
                        manual_note="版本切换新增节点，等待补料",
                        updated_by=operator_user_id,
                    )
                )
                continue

            old_node = old_node_map[code]
            old_node.definition_node_id = def_node.id
            old_node.node_name = def_node.node_name
            old_node.node_order = def_node.node_order
            if old_node.status == "RUNNING":
                old_node.status = "PENDING"
                old_node.manual_note = "版本切换后由运行中重置为待处理"
            old_node.updated_by = operator_user_id

        instance.workflow_definition_version_id = target_version_id
        instance.updated_by = operator_user_id

        refreshed_nodes = (
            db.query(WorkflowInstanceNode)
            .filter(WorkflowInstanceNode.workflow_instance_id == instance.id)
            .filter(WorkflowInstanceNode.node_code.in_(list(target_node_map.keys())))
            .order_by(WorkflowInstanceNode.node_order.asc())
            .all()
        )

        next_current = None
        for node in refreshed_nodes:
            if node.status in {"PENDING", "RUNNING", "BLOCKED"}:
                next_current = node.id
                break
        instance.current_node_id = next_current

        db.add(
            WorkflowTransitionLog(
                workflow_instance_id=instance.id,
                workflow_instance_node_id=instance.current_node_id,
                action="SWITCH_VERSION",
                from_status=str(old_version_id),
                to_status=str(target_version_id),
                is_overridden=False,
                operator_user_id=operator_user_id,
                note=f"版本切换: {old_version_id} -> {target_version_id}",
                created_at=datetime.now(),
            )
        )
        switched += 1

    return switched
