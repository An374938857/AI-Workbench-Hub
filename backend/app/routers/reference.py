from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_role
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.reference_service import (
    cleanup_reference_audit_logs,
    clear_selection,
    confirm_selection,
    ensure_reference_state,
    get_conversation_binding_context,
    get_or_build_catalog,
    get_reference_state,
    resolve_scope_snapshot_for_state,
)

router = APIRouter()


class BuildScopeRequest(BaseModel):
    conversation_id: int
    binding_type: str | None = None
    binding_id: int | None = None


class ConfirmSelectionRequest(BaseModel):
    conversation_id: int
    selected_file_ids: list[int] = Field(default_factory=list)
    mode: str = Field(..., pattern="^(persist_selection|persist_empty|turn_only_skip)$")


class ClearSelectionRequest(BaseModel):
    conversation_id: int


def _get_owned_conversation_or_error(
    conversation_id: int,
    user_id: int,
    db: Session,
) -> tuple[Conversation | None, ApiResponse | None]:
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conversation:
        return None, ApiResponse.error(40401, "对话不存在")
    return conversation, None


@router.post("/scope/build")
def build_scope(
    body: BuildScopeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation, error = _get_owned_conversation_or_error(
        body.conversation_id, current_user.id, db
    )
    if error:
        return error

    scope_snapshot_id, catalog = get_or_build_catalog(conversation, db, force_rebuild=True)
    db.commit()

    return ApiResponse.success(
        data={
            "scope_snapshot_id": scope_snapshot_id,
            "file_count": len(catalog),
        }
    )


@router.get("/panel")
def panel(
    conversation_id: int = Query(...),
    query: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation, error = _get_owned_conversation_or_error(
        conversation_id, current_user.id, db
    )
    if error:
        return error

    scope_snapshot_id, catalog = get_or_build_catalog(conversation, db, force_rebuild=False)
    state = ensure_reference_state(db, conversation.id, current_user.id)

    selected_ids = set(state.selected_file_ids or [])
    selected = [item for item in catalog if item.get("file_id") in selected_ids]
    binding = get_conversation_binding_context(db, conversation.id)

    db.commit()
    return ApiResponse.success(
        data={
            "scope_snapshot_id": scope_snapshot_id,
            "recommended": [],
            "selected": selected,
            "all_files": catalog,
            "binding": binding,
            "empty_mode": state.empty_mode,
            "selection_version": state.selection_version,
        }
    )


@router.post("/selection/confirm")
def selection_confirm(
    body: ConfirmSelectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation, error = _get_owned_conversation_or_error(
        body.conversation_id, current_user.id, db
    )
    if error:
        return error

    try:
        result = confirm_selection(
            db=db,
            conversation=conversation,
            selected_file_ids=body.selected_file_ids,
            mode=body.mode,
            user_id=current_user.id,
        )
    except ValueError as exc:
        db.rollback()
        return ApiResponse.error(40001, str(exc))

    db.commit()
    return ApiResponse.success(data=result)


@router.post("/selection/clear")
def selection_clear(
    body: ClearSelectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation, error = _get_owned_conversation_or_error(
        body.conversation_id, current_user.id, db
    )
    if error:
        return error

    result = clear_selection(db, conversation, current_user.id)
    db.commit()
    return ApiResponse.success(data=result)


@router.get("/state")
def get_state(
    conversation_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation, error = _get_owned_conversation_or_error(
        conversation_id, current_user.id, db
    )
    if error:
        return error

    state = get_reference_state(db, conversation.id)
    if not state:
        state = ensure_reference_state(db, conversation.id, current_user.id)
    effective_scope_snapshot_id = resolve_scope_snapshot_for_state(db, conversation, state)

    db.commit()

    return ApiResponse.success(
        data={
            "conversation_id": conversation.id,
            "scope_snapshot_id": effective_scope_snapshot_id,
            "selected_file_ids": state.selected_file_ids,
            "empty_mode": state.empty_mode,
            "selection_version": state.selection_version,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }
    )


@router.post("/admin/audit-log/cleanup")
def cleanup_audit_log(
    retention_days: int = 180,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    deleted = cleanup_reference_audit_logs(db, retention_days=retention_days)
    db.commit()
    return ApiResponse.success(data={"deleted_count": deleted, "retention_days": retention_days})
