from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_role
from app.models.asset import Asset
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinitionNode,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowInstanceNode,
    WorkflowTransitionLog,
)
from app.services.workflow_instance_service import (
    create_workflow_instance,
    get_published_version,
    refresh_requirement_status_from_instance,
)
from app.schemas.base import ApiResponse
from app.schemas.workflow_delivery import (
    RequirementCreate,
    RequirementUpdate,
    RequirementWorkflowBindingUpdate,
)

router = APIRouter()


def _requirement_to_dict(
    requirement: Requirement,
    instance_map: dict[int, WorkflowInstance] | None = None,
    instance_nodes_map: dict[int, list[WorkflowInstanceNode]] | None = None,
    definition_node_by_id: dict[int, WorkflowDefinitionNode] | None = None,
    definition_nodes_map: dict[int, list[WorkflowDefinitionNode]] | None = None,
    owner_map: dict[int, User] | None = None,
) -> dict:
    workflow_instance = instance_map.get(requirement.id) if instance_map else None
    workflow_nodes: list[dict] = []
    workflow_status = "UNBOUND" if not requirement.workflow_definition_id else "NOT_STARTED"
    if workflow_instance:
        workflow_status = workflow_instance.status
        node_items = (instance_nodes_map or {}).get(workflow_instance.id, [])
        workflow_nodes = [
            {
                "id": node.id,
                "node_code": node.node_code,
                "node_name": node.node_name,
                "node_order": node.node_order,
                "status": node.status,
                "skill_id": (definition_node_by_id or {}).get(node.definition_node_id).skill_id
                if (definition_node_by_id or {}).get(node.definition_node_id)
                else None,
            }
            for node in sorted(node_items, key=lambda item: item.node_order)
        ]
    elif requirement.workflow_definition_id and definition_nodes_map:
        definition_nodes = definition_nodes_map.get(requirement.workflow_definition_id, [])
        workflow_nodes = [
            {
                "id": None,
                "node_code": node.node_code,
                "node_name": node.node_name,
                "node_order": node.node_order,
                "status": "NOT_STARTED",
                "skill_id": node.skill_id,
            }
            for node in sorted(definition_nodes, key=lambda item: item.node_order)
        ]

    owner = (owner_map or {}).get(requirement.created_by)
    return {
        "id": requirement.id,
        "project_id": requirement.project_id,
        "title": requirement.title,
        "owner_user_id": requirement.created_by,
        "owner_name": owner.display_name if owner else f"用户#{requirement.created_by}",
        "priority": requirement.priority,
        "status": requirement.status,
        "workflow_definition_id": requirement.workflow_definition_id,
        "workflow_instance_id": workflow_instance.id if workflow_instance else requirement.workflow_instance_id,
        "workflow_status": workflow_status,
        "workflow_nodes": workflow_nodes,
        "due_date": requirement.due_date.isoformat() if requirement.due_date else None,
        "description": requirement.description,
        "created_at": requirement.created_at.isoformat() if requirement.created_at else None,
        "updated_at": requirement.updated_at.isoformat() if requirement.updated_at else None,
    }


@router.get("")
def get_requirements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: int | None = None,
    priority: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    owner_user_id: int | None = Query(None, ge=1),
    owner_keyword: str | None = None,
    due_date_start: date | None = None,
    due_date_end: date | None = None,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = db.query(Requirement)
    if project_id:
        query = query.filter(Requirement.project_id == project_id)
    if priority:
        query = query.filter(Requirement.priority == priority)
    if status:
        query = query.filter(Requirement.status == status)
    if keyword:
        query = query.filter(Requirement.title.like(f"%{keyword}%"))
    if owner_user_id:
        query = query.filter(Requirement.created_by == owner_user_id)
    if owner_keyword:
        like_pattern = f"%{owner_keyword}%"
        query = query.join(User, Requirement.created_by == User.id).filter(
            (User.display_name.like(like_pattern)) | (User.username.like(like_pattern))
        )
    if due_date_start:
        query = query.filter(Requirement.due_date >= due_date_start)
    if due_date_end:
        query = query.filter(Requirement.due_date <= due_date_end)

    total = query.count()
    items = query.order_by(Requirement.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    requirement_ids = [item.id for item in items]
    owner_user_ids = sorted({item.created_by for item in items})
    owner_map: dict[int, User] = {}
    if owner_user_ids:
        owner_items = db.query(User).filter(User.id.in_(owner_user_ids)).all()
        owner_map = {item.id: item for item in owner_items}

    latest_instance_map: dict[int, WorkflowInstance] = {}
    latest_instance_nodes_map: dict[int, list[WorkflowInstanceNode]] = {}
    definition_node_by_id: dict[int, WorkflowDefinitionNode] = {}
    definition_nodes_map: dict[int, list[WorkflowDefinitionNode]] = {}

    if requirement_ids:
        instances = (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.scope_type == "REQUIREMENT",
                WorkflowInstance.scope_id.in_(requirement_ids),
            )
            .order_by(WorkflowInstance.scope_id.asc(), WorkflowInstance.updated_at.desc())
            .all()
        )
        latest_instance_ids: list[int] = []
        for instance in instances:
            if instance.scope_id in latest_instance_map:
                continue
            latest_instance_map[instance.scope_id] = instance
            latest_instance_ids.append(instance.id)

        if latest_instance_ids:
            nodes = (
                db.query(WorkflowInstanceNode)
                .filter(WorkflowInstanceNode.workflow_instance_id.in_(latest_instance_ids))
                .all()
            )
            for node in nodes:
                latest_instance_nodes_map.setdefault(node.workflow_instance_id, []).append(node)
            definition_node_ids = sorted({item.definition_node_id for item in nodes})
            if definition_node_ids:
                definition_node_rows = (
                    db.query(WorkflowDefinitionNode)
                    .filter(WorkflowDefinitionNode.id.in_(definition_node_ids))
                    .all()
                )
                definition_node_by_id = {item.id: item for item in definition_node_rows}

        workflow_definition_ids = list(
            {
                item.workflow_definition_id
                for item in items
                if item.workflow_definition_id and item.id not in latest_instance_map
            }
        )
        if workflow_definition_ids:
            published_versions = (
                db.query(WorkflowDefinitionVersion)
                .filter(
                    WorkflowDefinitionVersion.workflow_definition_id.in_(workflow_definition_ids),
                    WorkflowDefinitionVersion.is_published.is_(True),
                )
                .all()
            )
            published_version_map: dict[int, WorkflowDefinitionVersion] = {}
            for version in published_versions:
                prev = published_version_map.get(version.workflow_definition_id)
                if prev is None or version.version_no > prev.version_no:
                    published_version_map[version.workflow_definition_id] = version

            version_ids = [version.id for version in published_version_map.values()]
            if version_ids:
                definition_nodes = (
                    db.query(WorkflowDefinitionNode)
                    .filter(WorkflowDefinitionNode.workflow_definition_version_id.in_(version_ids))
                    .all()
                )
                version_to_definition = {
                    version.id: version.workflow_definition_id for version in published_version_map.values()
                }
                for node in definition_nodes:
                    definition_id = version_to_definition.get(node.workflow_definition_version_id)
                    if definition_id:
                        definition_nodes_map.setdefault(definition_id, []).append(node)

    return ApiResponse.success(
        data={
            "items": [
                _requirement_to_dict(
                    item,
                    latest_instance_map,
                    latest_instance_nodes_map,
                    definition_node_by_id,
                    definition_nodes_map,
                    owner_map,
                )
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("")
def create_requirement(
    body: RequirementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        return ApiResponse.error(40401, "项目不存在")

    try:
        _ = get_published_version(db, body.workflow_definition_id, "REQUIREMENT")
    except HTTPException as exc:
        return ApiResponse.error(40001, str(exc))

    requirement = Requirement(
        project_id=body.project_id,
        title=body.title,
        priority=body.priority,
        workflow_definition_id=body.workflow_definition_id,
        due_date=body.due_date,
        description=body.description,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(requirement)
    db.flush()

    instance = create_workflow_instance(
        db=db,
        scope_type="REQUIREMENT",
        scope_id=requirement.id,
        workflow_definition_id=body.workflow_definition_id,
        operator_id=current_user.id,
    )
    requirement.workflow_instance_id = instance.id
    refresh_requirement_status_from_instance(db, requirement)

    db.commit()
    db.refresh(requirement)
    owner = db.query(User).filter(User.id == requirement.created_by).first()
    owner_map = {owner.id: owner} if owner else None
    return ApiResponse.success(data=_requirement_to_dict(requirement, owner_map=owner_map))


@router.get("/owner-options")
def get_requirement_owner_options(
    keyword: str | None = None,
    page_size: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = db.query(User).filter(User.is_active.is_(True))
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter((User.display_name.like(like_pattern)) | (User.username.like(like_pattern)))
    users = query.order_by(User.display_name.asc(), User.id.asc()).limit(page_size).all()
    return ApiResponse.success(
        data=[
            {
                "id": item.id,
                "display_name": item.display_name,
                "username": item.username,
            }
            for item in users
        ]
    )


@router.get("/{requirement_id}")
def get_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        return ApiResponse.error(40401, "需求不存在")
    owner = db.query(User).filter(User.id == requirement.created_by).first()
    owner_map = {owner.id: owner} if owner else None
    return ApiResponse.success(data=_requirement_to_dict(requirement, owner_map=owner_map))


@router.put("/{requirement_id}")
def update_requirement(
    requirement_id: int,
    body: RequirementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        return ApiResponse.error(40401, "需求不存在")

    if body.title is not None:
        requirement.title = body.title
    if body.owner_user_id is not None:
        owner = db.query(User).filter(User.id == body.owner_user_id).first()
        if not owner:
            return ApiResponse.error(40401, "负责人不存在")
        requirement.created_by = owner.id
    if body.priority is not None:
        requirement.priority = body.priority
    if body.status is not None:
        requirement.status = body.status
    if "due_date" in body.model_fields_set:
        requirement.due_date = body.due_date
    if "description" in body.model_fields_set:
        requirement.description = body.description
    requirement.updated_by = current_user.id

    db.commit()
    db.refresh(requirement)
    owner = db.query(User).filter(User.id == requirement.created_by).first()
    owner_map = {owner.id: owner} if owner else None
    return ApiResponse.success(data=_requirement_to_dict(requirement, owner_map=owner_map))


@router.put("/{requirement_id}/workflow-binding")
def bind_requirement_workflow(
    requirement_id: int,
    body: RequirementWorkflowBindingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        return ApiResponse.error(40401, "需求不存在")

    try:
        _ = get_published_version(db, body.workflow_definition_id, "REQUIREMENT")
    except HTTPException as exc:
        return ApiResponse.error(40001, str(exc))

    instance = create_workflow_instance(
        db=db,
        scope_type="REQUIREMENT",
        scope_id=requirement.id,
        workflow_definition_id=body.workflow_definition_id,
        operator_id=current_user.id,
    )
    requirement.workflow_definition_id = body.workflow_definition_id
    requirement.workflow_instance_id = instance.id
    requirement.updated_by = current_user.id
    refresh_requirement_status_from_instance(db, requirement)

    db.commit()
    db.refresh(requirement)
    owner = db.query(User).filter(User.id == requirement.created_by).first()
    owner_map = {owner.id: owner} if owner else None
    return ApiResponse.success(data=_requirement_to_dict(requirement, owner_map=owner_map))


@router.delete("/{requirement_id}")
def delete_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("user", "admin")),
):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        return ApiResponse.error(40401, "需求不存在")

    requirement.workflow_instance_id = None
    db.flush()

    requirement_instance_ids = [
        item.id
        for item in (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.scope_type == "REQUIREMENT",
                WorkflowInstance.scope_id == requirement_id,
            )
            .all()
        )
    ]
    if requirement_instance_ids:
        db.query(WorkflowTransitionLog).filter(
            WorkflowTransitionLog.workflow_instance_id.in_(requirement_instance_ids)
        ).delete(synchronize_session=False)
        db.query(WorkflowInstance).filter(
            WorkflowInstance.id.in_(requirement_instance_ids)
        ).update({"current_node_id": None}, synchronize_session=False)
        db.query(WorkflowInstance).filter(
            WorkflowInstance.id.in_(requirement_instance_ids)
        ).delete(synchronize_session=False)

    db.query(Asset).filter(
        Asset.scope_type == "REQUIREMENT",
        Asset.scope_id == requirement_id,
    ).delete(synchronize_session=False)

    db.delete(requirement)
    db.commit()
    return ApiResponse.success(data={"id": requirement_id}, message="需求已删除")
