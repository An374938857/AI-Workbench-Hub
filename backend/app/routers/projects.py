from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_role
from app.models.asset import Asset
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionNode,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowInstanceNode,
    WorkflowTransitionLog,
)
from app.schemas.base import ApiResponse
from app.schemas.workflow_delivery import (
    ProjectCreate,
    ProjectOwnersUpdate,
    ProjectUpdate,
    ProjectWorkflowBindingUpdate,
)

router = APIRouter()


def _project_to_dict(
    project: Project,
    instance_map: dict[int, WorkflowInstance] | None = None,
    instance_nodes_map: dict[int, list[WorkflowInstanceNode]] | None = None,
    definition_node_by_id: dict[int, WorkflowDefinitionNode] | None = None,
    definition_nodes_map: dict[int, list[WorkflowDefinitionNode]] | None = None,
) -> dict:
    workflow_instance = instance_map.get(project.id) if instance_map else None
    workflow_nodes: list[dict] = []
    workflow_status = "UNBOUND" if not project.workflow_definition_id else "NOT_STARTED"
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
    elif project.workflow_definition_id and definition_nodes_map:
        definition_nodes = definition_nodes_map.get(project.workflow_definition_id, [])
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

    return {
        "id": project.id,
        "name": project.name,
        "level": project.level,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "metis_url": project.metis_url,
        "workflow_definition_id": project.workflow_definition_id,
        "workflow_instance_id": workflow_instance.id if workflow_instance else None,
        "owner_user_ids": [user.id for user in project.owners],
        "workflow_status": workflow_status,
        "workflow_nodes": workflow_nodes,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _validate_workflow_binding(db: Session, workflow_definition_id: int, scope: str) -> None:
    definition = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.id == workflow_definition_id)
        .first()
    )
    if not definition:
        raise ValueError("流程定义不存在")
    if definition.scope != scope:
        raise ValueError("流程作用域不匹配")

    has_published = (
        db.query(WorkflowDefinitionVersion)
        .filter(
            WorkflowDefinitionVersion.workflow_definition_id == workflow_definition_id,
            WorkflowDefinitionVersion.is_published.is_(True),
        )
        .first()
    )
    if not has_published:
        raise ValueError("流程定义无已发布版本")


@router.get("")
def get_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    level: str | None = Query(None),
    owner_user_id: int | None = Query(None, ge=1),
    workflow_status: str | None = Query(None),
    end_date_start: date | None = Query(None),
    end_date_end: date | None = Query(None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    allowed_workflow_statuses = {"NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELED"}
    if workflow_status and workflow_status not in allowed_workflow_statuses:
        return ApiResponse.error(40001, "项目状态筛选值不合法")
    if end_date_start and end_date_end and end_date_end < end_date_start:
        return ApiResponse.error(40001, "结束日期范围不合法")

    query = db.query(Project)
    latest_workflow_status = (
        db.query(WorkflowInstance.status)
        .filter(
            WorkflowInstance.scope_type == "PROJECT",
            WorkflowInstance.scope_id == Project.id,
        )
        .order_by(WorkflowInstance.updated_at.desc(), WorkflowInstance.id.desc())
        .limit(1)
        .correlate(Project)
        .scalar_subquery()
    )

    if keyword:
        query = query.filter(Project.name.like(f"%{keyword}%"))
    if level:
        query = query.filter(Project.level == level)
    if owner_user_id:
        query = query.filter(Project.owners.any(User.id == owner_user_id))
    if workflow_status:
        if workflow_status == "NOT_STARTED":
            query = query.filter(
                and_(
                    Project.workflow_definition_id.isnot(None),
                    or_(
                        latest_workflow_status.is_(None),
                        latest_workflow_status == "NOT_STARTED",
                    ),
                )
            )
        else:
            query = query.filter(latest_workflow_status == workflow_status)
    if end_date_start:
        query = query.filter(Project.end_date >= end_date_start)
    if end_date_end:
        query = query.filter(Project.end_date <= end_date_end)

    total = query.count()
    items = query.order_by(Project.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    project_ids = [item.id for item in items]

    latest_instance_map: dict[int, WorkflowInstance] = {}
    latest_instance_nodes_map: dict[int, list[WorkflowInstanceNode]] = {}
    definition_node_by_id: dict[int, WorkflowDefinitionNode] = {}
    definition_nodes_map: dict[int, list[WorkflowDefinitionNode]] = {}

    if project_ids:
        instances = (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.scope_type == "PROJECT",
                WorkflowInstance.scope_id.in_(project_ids),
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
                _project_to_dict(
                    item,
                    latest_instance_map,
                    latest_instance_nodes_map,
                    definition_node_by_id,
                    definition_nodes_map,
                )
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("")
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    if body.start_date and body.end_date and body.end_date < body.start_date:
        return ApiResponse.error(40001, "结束时间不能早于开始时间")

    owners = db.query(User).filter(User.id.in_(body.owner_user_ids)).all()
    if len(owners) != len(set(body.owner_user_ids)):
        return ApiResponse.error(40001, "负责人包含无效用户")

    if body.workflow_definition_id:
        try:
            _validate_workflow_binding(db, body.workflow_definition_id, "PROJECT")
        except ValueError as exc:
            return ApiResponse.error(40001, str(exc))

    project = Project(
        name=body.name,
        level=body.level,
        start_date=body.start_date,
        end_date=body.end_date,
        metis_url=body.metis_url,
        workflow_definition_id=body.workflow_definition_id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    project.owners = owners
    db.add(project)
    db.commit()
    db.refresh(project)
    return ApiResponse.success(data=_project_to_dict(project))


@router.get("/{project_id}")
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ApiResponse.error(40401, "项目不存在")
    return ApiResponse.success(data=_project_to_dict(project))


@router.put("/{project_id}")
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ApiResponse.error(40401, "项目不存在")

    next_start_date = body.start_date if body.start_date is not None else project.start_date
    next_end_date = body.end_date if body.end_date is not None else project.end_date
    if next_start_date and next_end_date and next_end_date < next_start_date:
        return ApiResponse.error(40001, "结束时间不能早于开始时间")

    if body.name is not None:
        project.name = body.name
    if body.level is not None:
        project.level = body.level
    if body.start_date is not None:
        project.start_date = body.start_date
    if body.end_date is not None:
        project.end_date = body.end_date
    if body.metis_url is not None:
        project.metis_url = body.metis_url
    project.updated_by = current_user.id

    db.commit()
    db.refresh(project)
    return ApiResponse.success(data=_project_to_dict(project))


@router.put("/{project_id}/owners")
def update_project_owners(
    project_id: int,
    body: ProjectOwnersUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ApiResponse.error(40401, "项目不存在")

    owner_ids = set(body.owner_user_ids)
    if len(owner_ids) != len(body.owner_user_ids):
        return ApiResponse.error(40001, "负责人不可重复")

    owners = db.query(User).filter(User.id.in_(list(owner_ids))).all()
    if len(owners) != len(owner_ids):
        return ApiResponse.error(40001, "负责人包含无效用户")

    project.owners = owners
    project.updated_by = current_user.id
    db.commit()
    db.refresh(project)
    return ApiResponse.success(data=_project_to_dict(project))


@router.put("/{project_id}/workflow-binding")
def bind_project_workflow(
    project_id: int,
    body: ProjectWorkflowBindingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ApiResponse.error(40401, "项目不存在")

    try:
        _validate_workflow_binding(db, body.workflow_definition_id, "PROJECT")
    except ValueError as exc:
        return ApiResponse.error(40001, str(exc))

    project.workflow_definition_id = body.workflow_definition_id
    project.updated_by = current_user.id
    db.commit()
    db.refresh(project)
    return ApiResponse.success(data=_project_to_dict(project))


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("user", "admin")),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ApiResponse.error(40401, "项目不存在")

    related_requirement_count = (
        db.query(Requirement)
        .filter(Requirement.project_id == project_id)
        .count()
    )
    if related_requirement_count > 0:
        return ApiResponse.error(40001, f"项目下仍有 {related_requirement_count} 条需求，请先删除需求")

    project_instance_ids = [
        item.id
        for item in (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.scope_type == "PROJECT",
                WorkflowInstance.scope_id == project_id,
            )
            .all()
        )
    ]
    if project_instance_ids:
        db.query(WorkflowTransitionLog).filter(
            WorkflowTransitionLog.workflow_instance_id.in_(project_instance_ids)
        ).delete(synchronize_session=False)
        db.query(WorkflowInstance).filter(
            WorkflowInstance.id.in_(project_instance_ids)
        ).update({"current_node_id": None}, synchronize_session=False)
        db.query(WorkflowInstance).filter(
            WorkflowInstance.id.in_(project_instance_ids)
        ).delete(synchronize_session=False)

    db.query(Asset).filter(
        Asset.scope_type == "PROJECT",
        Asset.scope_id == project_id,
    ).delete(synchronize_session=False)

    db.delete(project)
    db.commit()
    return ApiResponse.success(data={"id": project_id}, message="项目已删除")
