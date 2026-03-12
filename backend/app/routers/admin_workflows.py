from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionNode,
    WorkflowDefinitionVersion,
)
from app.schemas.base import ApiResponse
from app.schemas.workflow_delivery import (
    WorkflowDefinitionCreate,
    WorkflowVersionCreate,
    WorkflowVersionNodesUpdate,
)
from app.services.workflow_version_service import switch_instances_to_version

router = APIRouter()


def _definition_to_dict(definition: WorkflowDefinition) -> dict:
    return {
        "id": definition.id,
        "name": definition.name,
        "code": definition.code,
        "scope": definition.scope,
        "description": definition.description,
        "status": definition.status,
        "created_at": definition.created_at.isoformat() if definition.created_at else None,
        "updated_at": definition.updated_at.isoformat() if definition.updated_at else None,
    }


def _version_to_dict(version: WorkflowDefinitionVersion) -> dict:
    return {
        "id": version.id,
        "workflow_definition_id": version.workflow_definition_id,
        "version_no": version.version_no,
        "version_label": version.version_label,
        "is_published": version.is_published,
        "status": "PUBLISHED" if version.is_published else "DRAFT",
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "published_by": version.published_by,
        "schema_json": version.schema_json,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


@router.get("/definitions")
def list_workflow_definitions(
    scope: str | None = Query(None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("provider", "admin")),
):
    query = db.query(WorkflowDefinition)
    if scope:
        query = query.filter(WorkflowDefinition.scope == scope)
    definitions = query.order_by(WorkflowDefinition.updated_at.desc()).all()
    return ApiResponse.success(data=[_definition_to_dict(item) for item in definitions])


@router.get("/definitions/{definition_id}")
def get_workflow_definition(
    definition_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("provider", "admin")),
):
    definition = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.id == definition_id)
        .first()
    )
    if not definition:
        return ApiResponse.error(40401, "流程定义不存在")

    versions = (
        db.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.workflow_definition_id == definition_id)
        .order_by(WorkflowDefinitionVersion.version_no.desc())
        .all()
    )
    return ApiResponse.success(
        data={
            **_definition_to_dict(definition),
            "versions": [_version_to_dict(item) for item in versions],
        }
    )


@router.get("/versions/{version_id}")
def get_workflow_version(
    version_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("provider", "admin")),
):
    version = (
        db.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.id == version_id)
        .first()
    )
    if not version:
        return ApiResponse.error(40401, "流程版本不存在")

    nodes = (
        db.query(WorkflowDefinitionNode)
        .filter(WorkflowDefinitionNode.workflow_definition_version_id == version_id)
        .order_by(WorkflowDefinitionNode.node_order.asc())
        .all()
    )
    return ApiResponse.success(
        data={
            **_version_to_dict(version),
            "nodes": [
                {
                    "id": node.id,
                    "node_code": node.node_code,
                    "node_name": node.node_name,
                    "node_order": node.node_order,
                    "skill_id": node.skill_id,
                    "input_mapping_json": node.input_mapping_json,
                    "output_type": node.output_type,
                    "retry_policy_json": node.retry_policy_json,
                }
                for node in nodes
            ],
        }
    )


@router.post("/definitions")
def create_workflow_definition(
    body: WorkflowDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    existing = (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.scope == body.scope,
            WorkflowDefinition.code == body.code,
        )
        .first()
    )
    if existing:
        return ApiResponse.error(40901, "同 scope 下流程 code 已存在")

    definition = WorkflowDefinition(
        name=body.name,
        code=body.code,
        scope=body.scope,
        description=body.description,
        status="ACTIVE",
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(definition)
    db.commit()
    db.refresh(definition)
    return ApiResponse.success(data={"id": definition.id})


@router.post("/definitions/{definition_id}/versions")
def create_workflow_version(
    definition_id: int,
    body: WorkflowVersionCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("provider", "admin")),
):
    definition = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.id == definition_id)
        .first()
    )
    if not definition:
        return ApiResponse.error(40401, "流程定义不存在")

    last_version = (
        db.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.workflow_definition_id == definition_id)
        .order_by(WorkflowDefinitionVersion.version_no.desc())
        .first()
    )
    if last_version and not body.source_version_id:
        last_nodes_count = (
            db.query(WorkflowDefinitionNode)
            .filter(WorkflowDefinitionNode.workflow_definition_version_id == last_version.id)
            .count()
        )
        if last_nodes_count == 0:
            return ApiResponse.error(40001, "当前最新版本没有任何节点，请先完善或删除该版本")

    source_version: WorkflowDefinitionVersion | None = None
    if body.source_version_id:
        source_version = (
            db.query(WorkflowDefinitionVersion)
            .filter(
                WorkflowDefinitionVersion.id == body.source_version_id,
                WorkflowDefinitionVersion.workflow_definition_id == definition_id,
            )
            .first()
        )
        if not source_version:
            return ApiResponse.error(40401, "源流程版本不存在")
    elif last_version:
        source_version = last_version

    next_no = 1 if not last_version else last_version.version_no + 1

    version = WorkflowDefinitionVersion(
        workflow_definition_id=definition_id,
        version_no=next_no,
        version_label=body.version_label,
        is_published=False,
        schema_json={},
    )
    db.add(version)
    db.flush()

    node_schema: list[dict] = []
    if source_version:
        source_nodes = (
            db.query(WorkflowDefinitionNode)
            .filter(WorkflowDefinitionNode.workflow_definition_version_id == source_version.id)
            .order_by(WorkflowDefinitionNode.node_order.asc())
            .all()
        )
        for node in source_nodes:
            cloned_node = WorkflowDefinitionNode(
                workflow_definition_version_id=version.id,
                node_code=node.node_code,
                node_name=node.node_name,
                node_order=node.node_order,
                skill_id=node.skill_id,
                input_mapping_json=node.input_mapping_json,
                output_type=node.output_type,
                retry_policy_json=node.retry_policy_json,
            )
            db.add(cloned_node)
            node_schema.append(
                {
                    "node_code": node.node_code,
                    "node_name": node.node_name,
                    "node_order": node.node_order,
                    "skill_id": node.skill_id,
                    "input_mapping_json": node.input_mapping_json,
                    "output_type": node.output_type,
                    "retry_policy_json": node.retry_policy_json,
                }
            )
    version.schema_json = {"nodes": node_schema}
    db.commit()
    db.refresh(version)
    return ApiResponse.success(data={"id": version.id, "version_no": version.version_no})


@router.put("/versions/{version_id}/nodes")
def update_version_nodes(
    version_id: int,
    body: WorkflowVersionNodesUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("provider", "admin")),
):
    version = (
        db.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.id == version_id)
        .first()
    )
    if not version:
        return ApiResponse.error(40401, "流程版本不存在")
    if version.is_published:
        return ApiResponse.error(40001, "已发布版本不可编辑节点")
    if len(body.nodes) == 0:
        return ApiResponse.error(40001, "流程版本未配置节点")

    normalized_codes = [node.node_code.strip() for node in body.nodes]
    if len(normalized_codes) != len(set(normalized_codes)):
        return ApiResponse.error(40001, "节点编码不能重复")
    orders = [node.node_order for node in body.nodes]
    if len(orders) != len(set(orders)):
        return ApiResponse.error(40001, "节点顺序不能重复")

    db.query(WorkflowDefinitionNode).filter(
        WorkflowDefinitionNode.workflow_definition_version_id == version_id
    ).delete(synchronize_session=False)

    node_schema = []
    for node in body.nodes:
        row = WorkflowDefinitionNode(
            workflow_definition_version_id=version_id,
            node_code=node.node_code.strip(),
            node_name=node.node_name,
            node_order=node.node_order,
            skill_id=node.skill_id,
            input_mapping_json=node.input_mapping_json,
            output_type=node.output_type,
            retry_policy_json=node.retry_policy_json,
        )
        db.add(row)
        node_schema.append(node.model_dump())

    version.schema_json = {"nodes": node_schema}
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return ApiResponse.error(40001, "节点数据存在重复，请检查节点编码与顺序")
    return ApiResponse.success(message="节点更新成功")


@router.post("/versions/{version_id}/publish")
def publish_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    version = (
        db.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.id == version_id)
        .first()
    )
    if not version:
        return ApiResponse.error(40401, "流程版本不存在")

    nodes_count = (
        db.query(WorkflowDefinitionNode)
        .filter(WorkflowDefinitionNode.workflow_definition_version_id == version_id)
        .count()
    )
    if nodes_count == 0:
        return ApiResponse.error(40001, "流程版本未配置节点")

    db.query(WorkflowDefinitionVersion).filter(
        WorkflowDefinitionVersion.workflow_definition_id == version.workflow_definition_id,
        WorkflowDefinitionVersion.is_published.is_(True),
    ).update({"is_published": False}, synchronize_session=False)

    version.is_published = True
    version.published_at = datetime.now()
    version.published_by = current_user.id
    switched_count = switch_instances_to_version(
        db=db,
        workflow_definition_id=version.workflow_definition_id,
        target_version_id=version.id,
        operator_user_id=current_user.id,
    )
    db.commit()
    return ApiResponse.success(data={"switched_instances": switched_count}, message="发布成功")


@router.delete("/versions/{version_id}")
def delete_draft_version(
    version_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("provider", "admin")),
):
    version = (
        db.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.id == version_id)
        .first()
    )
    if not version:
        return ApiResponse.error(40401, "流程版本不存在")
    if version.is_published:
        return ApiResponse.error(40001, "已发布版本不可删除")

    versions_count = (
        db.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.workflow_definition_id == version.workflow_definition_id)
        .count()
    )
    if versions_count <= 1:
        return ApiResponse.error(40001, "至少保留一个流程版本")

    db.delete(version)
    db.commit()
    return ApiResponse.success(message="草稿删除成功")


@router.post("/versions/{version_id}/deprecate")
def deprecate_definition(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    version = (
        db.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.id == version_id)
        .first()
    )
    if not version:
        return ApiResponse.error(40401, "流程版本不存在")

    definition = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.id == version.workflow_definition_id)
        .first()
    )
    if not definition:
        raise HTTPException(status_code=404, detail="流程定义不存在")

    definition.status = "DEPRECATED"
    definition.updated_by = current_user.id
    db.commit()
    return ApiResponse.success(message="废弃成功")


@router.post("/definitions/{definition_id}/deprecate")
def deprecate_workflow_definition(
    definition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    definition = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.id == definition_id)
        .first()
    )
    if not definition:
        return ApiResponse.error(40401, "流程定义不存在")

    definition.status = "DEPRECATED"
    definition.updated_by = current_user.id
    db.commit()
    return ApiResponse.success(message="废弃成功")


@router.post("/definitions/{definition_id}/activate")
def activate_definition(
    definition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    definition = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.id == definition_id)
        .first()
    )
    if not definition:
        return ApiResponse.error(40401, "流程定义不存在")

    definition.status = "ACTIVE"
    definition.updated_by = current_user.id
    db.commit()
    return ApiResponse.success(message="重新启用成功")
