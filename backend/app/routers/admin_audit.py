from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.audit_service import AuditArchiveTask, AuditMetricsService, AuditQueryService

router = APIRouter()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/conversations")
def list_audit_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    user_id: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    model_name: Optional[str] = None,
    is_abnormal: Optional[bool] = None,
    skill_id: Optional[int] = None,
    mcp_tool: Optional[str] = None,
    conversation_status: Optional[str] = None,
    tag_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    service = AuditQueryService(db)
    data = service.list_conversations(
        page=page,
        page_size=page_size,
        user_id=user_id,
        start_time=_parse_datetime(start_time),
        end_time=_parse_datetime(end_time),
        model_name=model_name,
        is_abnormal=is_abnormal,
        skill_id=skill_id,
        mcp_tool=mcp_tool,
        conversation_status=conversation_status,
        tag_id=tag_id,
    )
    return ApiResponse.success(data=data)


@router.get("/conversations/{conversation_id}/timeline")
def get_conversation_timeline(
    conversation_id: int,
    trace_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    service = AuditQueryService(db)
    data = service.get_timeline(conversation_id=conversation_id, trace_id=trace_id)
    return ApiResponse.success(data=data)


@router.get("/conversations/{conversation_id}/rounds/{round_no}")
def get_round_detail(
    conversation_id: int,
    round_no: int,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    service = AuditQueryService(db)
    data = service.get_round_detail(conversation_id=conversation_id, round_no=round_no)
    return ApiResponse.success(data=data)


@router.post("/export")
def create_audit_export(
    body: dict,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    export_format = body.get("format", "ndjson")
    if export_format not in {"ndjson", "json_array"}:
        raise HTTPException(status_code=400, detail="format 仅支持 ndjson 或 json_array")

    service = AuditQueryService(db)
    task_id = service.create_export_task(
        filters=body.get("filters", {}),
        export_format=export_format,
    )
    return ApiResponse.success(data={"task_id": task_id})


@router.get("/export/{task_id}")
def get_audit_export_task(
    task_id: str,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    service = AuditQueryService(db)
    data = service.get_export_task(task_id)
    return ApiResponse.success(data=data)


@router.get("/export/{task_id}/download")
def download_audit_export(
    task_id: str,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    service = AuditQueryService(db)
    filepath = service.get_export_file(task_id)
    if not filepath:
        raise HTTPException(status_code=404, detail="导出文件不存在")
    return FileResponse(filepath, filename=filepath.split("/")[-1], media_type="application/octet-stream")


@router.get("/metrics/overview")
def get_audit_metrics_overview(
    window: str = Query("day", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    service = AuditMetricsService(db)
    data = service.overview(window)
    return ApiResponse.success(data=data)


@router.get("/replay/{trace_id}")
def replay_trace(
    trace_id: str,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    query_service = AuditQueryService(db)
    data = query_service.get_replay(trace_id)
    if not data.get("events"):
        archive_task = AuditArchiveTask(db)
        restored = archive_task.restore_by_trace(trace_id)
        data = {"trace_id": trace_id, "events": restored}
    return ApiResponse.success(data=data)
