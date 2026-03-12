from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.user import User
from app.models.workflow import WorkflowDefinition, WorkflowDefinitionVersion
from app.schemas.base import ApiResponse

router = APIRouter()


@router.get("")
def list_published_workflow_definitions(
    scope: str = Query(..., pattern=r"^(PROJECT|REQUIREMENT)$"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    definitions = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.scope == scope)
        .order_by(WorkflowDefinition.updated_at.desc())
        .all()
    )

    items = []
    for definition in definitions:
        version = (
            db.query(WorkflowDefinitionVersion)
            .filter(
                WorkflowDefinitionVersion.workflow_definition_id == definition.id,
                WorkflowDefinitionVersion.is_published.is_(True),
            )
            .order_by(WorkflowDefinitionVersion.version_no.desc())
            .first()
        )
        if not version:
            continue
        items.append(
            {
                "id": definition.id,
                "name": definition.name,
                "code": definition.code,
                "scope": definition.scope,
                "description": definition.description,
                "published_version_id": version.id,
                "published_version_no": version.version_no,
            }
        )

    return ApiResponse.success(data=items)
