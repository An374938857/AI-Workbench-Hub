import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.models.asset import Asset
from app.models.model_provider import ModelItem
from app.models.reference import FileLightIndex, ReferenceAuditLog
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.embedding_governance import (
    get_embedding_config,
    list_rebuild_task_items,
    list_rebuild_tasks,
    mark_task_queued,
    request_cancel_rebuild_task,
    retry_failed_rebuild_task,
    update_embedding_config,
)
from app.services.embedding_rebuild_runtime import get_embedding_rebuild_runtime
from app.services.file_service import extract_text

router = APIRouter()

TEXT_ROUTE_EXTENSIONS = {
    "txt", "md", "markdown", "json", "csv", "tsv", "py", "js", "ts", "tsx", "jsx",
    "java", "go", "rs", "sql", "html", "xml", "yaml", "yml",
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
}
MULTIMODAL_ROUTE_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp", "gif", "bmp",
    "mp4", "mov", "avi", "mkv", "webm", "mpeg", "mpg",
}
CHUNK_SIZE = 900
CHUNK_OVERLAP = 180


class EmbeddingConfigUpdateRequest(BaseModel):
    global_default_text_embedding_model_id: Optional[int] = None
    global_default_multimodal_embedding_model_id: Optional[int] = None
    rebuild_index: bool = False


def _safe_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _asset_file_name(asset: Asset) -> str:
    if asset.title:
        return asset.title
    if asset.file_ref:
        return os.path.basename(asset.file_ref)
    return f"asset-{asset.id}"


def _asset_extension(asset: Asset) -> str:
    if asset.file_ref:
        return Path(asset.file_ref).suffix.lower().lstrip(".")
    return Path(_asset_file_name(asset)).suffix.lower().lstrip(".")


def _route_asset(asset: Asset) -> str:
    ext = _asset_extension(asset)
    if ext in TEXT_ROUTE_EXTENSIONS:
        return "TEXT"
    if ext in MULTIMODAL_ROUTE_EXTENSIONS:
        return "MULTIMODAL"
    if asset.asset_type in {"MARKDOWN"}:
        return "TEXT"
    return "MULTIMODAL"


def _asset_file_path(asset: Asset) -> Optional[Path]:
    if not asset.file_ref:
        return None
    file_path = (Path.cwd() / asset.file_ref).resolve()
    if file_path.exists() and file_path.is_file():
        return file_path
    return None


def _extract_asset_text(asset: Asset) -> tuple[str, str]:
    file_path = _asset_file_path(asset)
    ext = _asset_extension(asset)
    if file_path and ext:
        try:
            extracted = extract_text(str(file_path), ext)
            if extracted.strip():
                return extracted, "FILE_EXTRACT"
        except Exception:
            pass

    if _safe_text(asset.snapshot_markdown):
        return asset.snapshot_markdown or "", "SNAPSHOT"
    if _safe_text(asset.content):
        return asset.content or "", "CONTENT"

    file_name = _asset_file_name(asset)
    meta = f"{file_name}\nasset_type={asset.asset_type}\nscope={asset.scope_type}:{asset.scope_id}"
    return meta, "METADATA"


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict[str, Any]]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []

    chunks: list[dict[str, Any]] = []
    if len(normalized) <= size:
        return [{"chunk_no": 1, "start": 0, "end": len(normalized), "chars": len(normalized), "text": normalized}]

    start = 0
    chunk_no = 1
    while start < len(normalized):
        end = min(len(normalized), start + size)
        content = normalized[start:end]
        chunks.append(
            {
                "chunk_no": chunk_no,
                "start": start,
                "end": end,
                "chars": len(content),
                "text": content,
            }
        )
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
        chunk_no += 1
    return chunks


def _embedding_sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_range_window(
    range_key: str,
    start_time: Optional[datetime],
    end_time: Optional[datetime],
) -> tuple[datetime, datetime, str]:
    now = datetime.now()
    normalized = (range_key or "7d").strip().lower()
    if normalized == "24h":
        return now - timedelta(hours=24), now, "24h"
    if normalized == "30d":
        return now - timedelta(days=30), now, "30d"
    if normalized == "custom":
        if not start_time or not end_time:
            raise ValueError("自定义时间范围需同时传入 start_time 和 end_time")
        if end_time <= start_time:
            raise ValueError("end_time 必须晚于 start_time")
        return start_time, end_time, "custom"
    return now - timedelta(days=7), now, "7d"


@router.get("/config")
def get_embedding_model_config(
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    return ApiResponse.success(data=get_embedding_config(db))


@router.put("/config")
@router.post("/config")
def update_embedding_model_config(
    body: EmbeddingConfigUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    try:
        payload = update_embedding_config(
            db=db,
            user_id=user.id,
            text_model_id=body.global_default_text_embedding_model_id,
            multimodal_model_id=body.global_default_multimodal_embedding_model_id,
            rebuild_index=body.rebuild_index,
        )
        db.commit()
        return ApiResponse.success(data=payload)
    except ValueError as exc:
        db.rollback()
        return ApiResponse.error(40001, str(exc))
    except Exception as exc:
        db.rollback()
        return ApiResponse.error(50001, f"更新 embedding 配置失败: {exc}")


@router.get("/rebuild/tasks")
def list_embedding_rebuild_tasks(
    limit: int = 20,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    return ApiResponse.success(data=list_rebuild_tasks(db, limit=limit))


@router.get("/rebuild/tasks/{task_id}/items")
def list_embedding_rebuild_task_items(
    task_id: int,
    limit: int = Query(100),
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    try:
        return ApiResponse.success(data=list_rebuild_task_items(db, task_id, limit=limit))
    except ValueError as exc:
        return ApiResponse.error(40401, str(exc))


@router.post("/rebuild/tasks/{task_id}/start")
async def start_embedding_rebuild(
    task_id: int,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    try:
        payload = mark_task_queued(db, task_id)
        db.commit()
        await get_embedding_rebuild_runtime().start_task(task_id)
        return ApiResponse.success(data=payload)
    except ValueError as exc:
        db.rollback()
        return ApiResponse.error(40401, str(exc))
    except Exception as exc:
        db.rollback()
        return ApiResponse.error(50001, f"启动重建任务失败: {exc}")


@router.post("/rebuild/tasks/{task_id}/retry-failed")
async def retry_failed_embedding_rebuild(
    task_id: int,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    try:
        payload = retry_failed_rebuild_task(db, task_id)
        db.commit()
        await get_embedding_rebuild_runtime().start_task(task_id)
        return ApiResponse.success(data=payload)
    except ValueError as exc:
        db.rollback()
        return ApiResponse.error(40401, str(exc))
    except Exception as exc:
        db.rollback()
        return ApiResponse.error(50001, f"重试失败项失败: {exc}")


@router.post("/rebuild/tasks/{task_id}/cancel")
def cancel_embedding_rebuild(
    task_id: int,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    try:
        payload = request_cancel_rebuild_task(db, task_id)
        db.commit()
        return ApiResponse.success(data=payload)
    except ValueError as exc:
        db.rollback()
        return ApiResponse.error(40401, str(exc))
    except Exception as exc:
        db.rollback()
        return ApiResponse.error(50001, f"取消重建任务失败: {exc}")


@router.get("/rebuild/tasks/stream")
async def stream_embedding_rebuild_tasks(
    _u: User = Depends(require_role("admin")),
):
    runtime = get_embedding_rebuild_runtime()
    subscriber = await runtime.subscribe()

    async def generate():
        try:
            while True:
                item = await subscriber.get()
                yield _embedding_sse_event(item.get("event", "task_update"), item.get("data", {}))
        except asyncio.CancelledError:
            raise
        finally:
            await runtime.unsubscribe(subscriber)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/files")
def list_embedding_files(
    keyword: Optional[str] = Query(default=None),
    status: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    query = db.query(Asset)
    if keyword:
        like_keyword = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                Asset.title.ilike(like_keyword),
                Asset.file_ref.ilike(like_keyword),
                Asset.source_url.ilike(like_keyword),
                Asset.node_code.ilike(like_keyword),
            )
        )

    assets = query.order_by(Asset.id.desc()).all()
    if not assets:
        return ApiResponse.success(
            data={
                "list": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0},
                "summary": {"embedded": 0, "not_embedded": 0, "failed": 0},
            }
        )

    file_ids = [asset.id for asset in assets]
    index_rows = db.query(FileLightIndex).filter(FileLightIndex.file_id.in_(file_ids)).all()
    index_map: dict[tuple[int, str], FileLightIndex] = {
        (row.file_id, row.embedding_type): row for row in index_rows
    }

    model_ids = {
        int(row.embedding_model_id)
        for row in index_rows
        if row.embedding_model_id is not None
    }
    model_name_map: dict[int, str] = {}
    if model_ids:
        model_rows = db.query(ModelItem.id, ModelItem.model_name).filter(ModelItem.id.in_(model_ids)).all()
        model_name_map = {int(row[0]): str(row[1]) for row in model_rows}

    records: list[dict[str, Any]] = []
    summary = {"embedded": 0, "not_embedded": 0, "failed": 0}
    for asset in assets:
        route_type = _route_asset(asset)
        row = index_map.get((asset.id, route_type))
        index_status = row.index_status if row else "PENDING"
        is_embedded = bool(row and row.index_status == "SUCCEEDED")

        if row and row.index_status == "FAILED":
            summary["failed"] += 1
        if is_embedded:
            summary["embedded"] += 1
        else:
            summary["not_embedded"] += 1

        if status == "embedded" and not is_embedded:
            continue
        if status == "not_embedded" and is_embedded:
            continue
        if status == "failed" and (not row or row.index_status != "FAILED"):
            continue

        model_id = int(row.embedding_model_id) if row and row.embedding_model_id is not None else None
        records.append(
            {
                "file_id": asset.id,
                "file_name": _asset_file_name(asset),
                "asset_type": asset.asset_type,
                "scope_type": asset.scope_type,
                "scope_id": asset.scope_id,
                "node_code": asset.node_code,
                "route_type": route_type,
                "embedding_type": route_type,
                "is_embedded": is_embedded,
                "index_status": index_status,
                "embedding_model_id": model_id,
                "embedding_model_name": model_name_map.get(model_id) if model_id else None,
                "embedding_dim": row.embedding_dim if row else None,
                "content_source": None,
                "summary": row.summary if row else None,
                "last_error": row.last_error if row else None,
                "index_version": row.index_version if row else None,
                "vector_ref": row.vector_ref if row else None,
                "indexed_at": row.indexed_at.isoformat() if row and row.indexed_at else None,
                "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
            }
        )

    total = len(records)
    start = (page - 1) * page_size
    end = start + page_size
    sliced = records[start:end]

    return ApiResponse.success(
        data={
            "list": sliced,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "summary": summary,
        }
    )


@router.get("/files/{file_id}/detail")
def get_embedding_file_detail(
    file_id: int,
    chunk_size: int = Query(default=CHUNK_SIZE, ge=200, le=4000),
    chunk_overlap: int = Query(default=CHUNK_OVERLAP, ge=0, le=1000),
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    asset = db.query(Asset).filter(Asset.id == file_id).first()
    if not asset:
        return ApiResponse.error(40401, "文件不存在")

    route_type = _route_asset(asset)
    row = (
        db.query(FileLightIndex)
        .filter(FileLightIndex.file_id == asset.id, FileLightIndex.embedding_type == route_type)
        .first()
    )

    model_name = None
    if row and row.embedding_model_id is not None:
        model = db.query(ModelItem).filter(ModelItem.id == row.embedding_model_id).first()
        model_name = model.model_name if model else None

    vector_payload = None
    if row and row.vector_ref:
        path = (Path.cwd() / row.vector_ref).resolve()
        if path.exists() and path.is_file():
            try:
                raw_payload = json.loads(path.read_text(encoding="utf-8"))
                vector_payload = {
                    "task_id": raw_payload.get("task_id"),
                    "file_id": raw_payload.get("file_id"),
                    "embedding_type": raw_payload.get("embedding_type"),
                    "target_model_id": raw_payload.get("target_model_id"),
                    "summary": raw_payload.get("summary"),
                    "content_source": raw_payload.get("content_source"),
                    "updated_at": raw_payload.get("updated_at"),
                }
            except Exception:
                vector_payload = None

    extracted_text, extracted_source = _extract_asset_text(asset)
    chunks = _chunk_text(extracted_text, size=chunk_size, overlap=chunk_overlap)

    data = {
        "file": {
            "file_id": asset.id,
            "file_name": _asset_file_name(asset),
            "asset_type": asset.asset_type,
            "scope_type": asset.scope_type,
            "scope_id": asset.scope_id,
            "node_code": asset.node_code,
            "source_url": asset.source_url,
            "file_ref": asset.file_ref,
            "route_type": route_type,
            "content_source": extracted_source,
            "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
        },
        "embedding": {
            "is_embedded": bool(row and row.index_status == "SUCCEEDED"),
            "index_status": row.index_status if row else "PENDING",
            "embedding_model_id": row.embedding_model_id if row else None,
            "embedding_model_name": model_name,
            "embedding_dim": row.embedding_dim if row else None,
            "index_version": row.index_version if row else None,
            "last_error": row.last_error if row else None,
            "indexed_at": row.indexed_at.isoformat() if row and row.indexed_at else None,
            "summary": row.summary if row else None,
            "vector_ref": row.vector_ref if row else None,
            "vector_payload": vector_payload,
        },
        "chunking": {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunk_count": len(chunks),
            "total_chars": len(extracted_text),
            "chunks": chunks,
        },
    }
    return ApiResponse.success(data=data)


@router.get("/recall/metrics")
def get_recall_metrics(
    range_key: str = Query(default="7d", alias="range"),
    start_time: Optional[datetime] = Query(default=None),
    end_time: Optional[datetime] = Query(default=None),
    top_n: int = Query(default=20, ge=5, le=100),
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    try:
        window_start, window_end, normalized_range = _parse_range_window(range_key, start_time, end_time)
    except ValueError as exc:
        return ApiResponse.error(40001, str(exc))

    logs = (
        db.query(ReferenceAuditLog)
        .filter(
            ReferenceAuditLog.created_at >= window_start,
            ReferenceAuditLog.created_at <= window_end,
        )
        .order_by(ReferenceAuditLog.created_at.asc())
        .all()
    )

    total_requests = len(logs)
    successful_requests = 0
    latency_values: list[float] = []
    selected_count_values: list[int] = []
    hit_bins = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
    file_counter: Counter[int] = Counter()

    trend_map: dict[str, dict[str, int]] = {}
    use_hour_bucket = normalized_range == "24h"

    for log in logs:
        selected_ids = log.final_selected_ids if isinstance(log.final_selected_ids, list) else []
        selected_count = len(selected_ids)
        selected_count_values.append(selected_count)

        if selected_count > 0:
            successful_requests += 1
            file_counter.update([int(fid) for fid in selected_ids if isinstance(fid, int) or str(fid).isdigit()])

        if selected_count <= 4:
            hit_bins[str(selected_count)] += 1
        else:
            hit_bins["5+"] += 1

        token_usage = log.token_usage_json if isinstance(log.token_usage_json, dict) else {}
        raw_latency = token_usage.get("reference_assembly_ms", token_usage.get("recall_latency_ms"))
        if isinstance(raw_latency, (int, float)) and raw_latency >= 0:
            latency_values.append(float(raw_latency))

        bucket = log.created_at.strftime("%Y-%m-%d %H:00") if use_hour_bucket else log.created_at.strftime("%Y-%m-%d")
        if bucket not in trend_map:
            trend_map[bucket] = {"requests": 0, "success": 0}
        trend_map[bucket]["requests"] += 1
        if selected_count > 0:
            trend_map[bucket]["success"] += 1

    success_rate = round((successful_requests / total_requests) if total_requests else 0.0, 4)
    avg_latency_ms = round(sum(latency_values) / len(latency_values), 2) if latency_values else None
    avg_hit_count = round(sum(selected_count_values) / len(selected_count_values), 2) if selected_count_values else 0.0

    top_file_ids = [item[0] for item in file_counter.most_common(top_n)]
    top_files: list[dict[str, Any]] = []
    if top_file_ids:
        assets = db.query(Asset).filter(Asset.id.in_(top_file_ids)).all()
        asset_map = {asset.id: asset for asset in assets}
        for file_id, hit_count in file_counter.most_common(top_n):
            asset = asset_map.get(file_id)
            top_files.append(
                {
                    "file_id": file_id,
                    "file_name": _asset_file_name(asset) if asset else f"asset-{file_id}",
                    "hit_count": hit_count,
                    "scope_type": asset.scope_type if asset else None,
                    "scope_id": asset.scope_id if asset else None,
                    "node_code": asset.node_code if asset else None,
                }
            )

    trend = [
        {"bucket": bucket, "requests": data["requests"], "success": data["success"]}
        for bucket, data in sorted(trend_map.items(), key=lambda item: item[0])
    ]

    return ApiResponse.success(
        data={
            "window": {
                "range": normalized_range,
                "start_time": window_start.isoformat(),
                "end_time": window_end.isoformat(),
            },
            "overview": {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "success_rate": success_rate,
                "avg_recall_latency_ms": avg_latency_ms,
            },
            "hit_distribution": {
                "bins": hit_bins,
                "avg_hit_count": avg_hit_count,
            },
            "top_files": top_files,
            "trend": trend,
        }
    )
