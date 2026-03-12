from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.asset import Asset
from app.models.model_provider import ModelItem, ModelProvider
from app.models.reference import (
    EmbeddingRebuildTask,
    EmbeddingRebuildTaskItem,
    FileLightIndex,
)
from app.models.system_config import SystemConfig
from app.services.file_service import extract_text
from app.services.llm.provider_factory import ProviderFactory

TEXT_EMBEDDING_KEY = "global_default_text_embedding_model_id"
MULTIMODAL_EMBEDDING_KEY = "global_default_multimodal_embedding_model_id"

TEXT_ROUTE_EXTENSIONS = {
    "txt", "md", "markdown", "json", "csv", "tsv", "py", "js", "ts", "tsx", "jsx",
    "java", "go", "rs", "sql", "html", "xml", "yaml", "yml",
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
}
MULTIMODAL_ROUTE_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp", "gif", "bmp",
    "mp4", "mov", "avi", "mkv", "webm", "mpeg", "mpg",
}
ACTIVE_TASK_STATUSES = {"QUEUED", "RUNNING"}
TERMINAL_TASK_STATUSES = {"SUCCEEDED", "FAILED", "PARTIAL_FAILED", "CANCELLED"}
RETRYABLE_ITEM_STATUSES = {"PENDING", "RETRYABLE_FAILED"}
MAX_ITEM_ATTEMPTS = 3
BATCH_SIZE = 300
EMBED_SUB_BATCH_SIZE = 25
EMBED_CONCURRENCY = 4
VECTOR_ROOT = Path.cwd() / "backend" / "uploads" / "generated" / "embedding_vectors"


@dataclass
class PreparedEmbeddingInput:
    item_id: int
    file_id: int
    route_type: str
    content_source: str
    summary: str
    text_input: str
    multimodal_input: dict[str, Any]


def _mime_type_for_extension(ext: str) -> str:
    mapping = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "avi": "video/x-msvideo",
        "mkv": "video/x-matroska",
        "webm": "video/webm",
        "mpeg": "video/mpeg",
        "mpg": "video/mpeg",
    }
    return mapping.get(ext, "application/octet-stream")


def _capability_tags(model: ModelItem) -> list[str]:
    tags = model.capability_tags or []
    if not isinstance(tags, list):
        return []
    return [str(t).lower() for t in tags]


def _is_text_embedding_model(model: ModelItem) -> bool:
    tags = _capability_tags(model)
    return "text_embedding" in tags or "embedding" in tags


def _is_multimodal_embedding_model(model: ModelItem) -> bool:
    tags = _capability_tags(model)
    return "multimodal_embedding" in tags or "embedding" in tags


def _get_config_record(db: Session, key: str) -> Optional[SystemConfig]:
    return db.query(SystemConfig).filter(SystemConfig.key == key).first()


def _get_config_int(db: Session, key: str) -> Optional[int]:
    record = _get_config_record(db, key)
    if not record or record.value is None:
        return None
    try:
        return int(record.value)
    except Exception:
        return None


def _set_config_int(db: Session, key: str, value: Optional[int], updated_by: Optional[int]) -> None:
    record = _get_config_record(db, key)
    if not record:
        record = SystemConfig(key=key, description=f"{key}")
        db.add(record)
    record.set_value(value if value is not None else None)
    record.updated_by = updated_by


def _serialize_model(model: ModelItem) -> dict:
    provider = model.provider
    return {
        "id": model.id,
        "provider_id": model.provider_id,
        "provider_name": provider.provider_name if provider else "",
        "model_name": model.model_name,
        "display_name": f"{provider.provider_name if provider else 'Provider'} / {model.model_name}",
        "capability_tags": model.capability_tags or [],
        "is_enabled": model.is_enabled,
    }


def get_embedding_config(db: Session) -> dict:
    models = (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(ModelItem.is_enabled == True, ModelProvider.is_enabled == True)
        .order_by(ModelProvider.id, ModelItem.id)
        .all()
    )
    text_candidates = [_serialize_model(m) for m in models if _is_text_embedding_model(m)]
    multimodal_candidates = [_serialize_model(m) for m in models if _is_multimodal_embedding_model(m)]

    return {
        "global_default_text_embedding_model_id": _get_config_int(db, TEXT_EMBEDDING_KEY),
        "global_default_multimodal_embedding_model_id": _get_config_int(db, MULTIMODAL_EMBEDDING_KEY),
        "text_candidates": text_candidates,
        "multimodal_candidates": multimodal_candidates,
    }


def _validate_embedding_model(db: Session, model_id: Optional[int], embedding_type: str) -> None:
    if model_id is None:
        return
    model = (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(ModelItem.id == model_id, ModelItem.is_enabled == True, ModelProvider.is_enabled == True)
        .first()
    )
    if not model:
        raise ValueError("目标 embedding 模型不存在或不可用")

    if embedding_type == "TEXT" and not _is_text_embedding_model(model):
        raise ValueError("所选模型不具备文本 embedding 能力")
    if embedding_type == "MULTIMODAL" and not _is_multimodal_embedding_model(model):
        raise ValueError("所选模型不具备多模态 embedding 能力")


def _asset_file_name(asset: Asset) -> str:
    if asset.title:
        return asset.title
    if asset.file_ref:
        return os.path.basename(asset.file_ref)
    return f"asset-{asset.id}"


def _asset_extension(asset: Asset) -> str:
    if asset.file_ref:
        return Path(asset.file_ref).suffix.lower().lstrip(".")
    file_name = _asset_file_name(asset)
    return Path(file_name).suffix.lower().lstrip(".")


def _asset_file_path(asset: Asset) -> Optional[Path]:
    if not asset.file_ref:
        return None
    file_path = (Path.cwd() / asset.file_ref).resolve()
    if file_path.exists() and file_path.is_file():
        return file_path
    return None


def _route_asset(asset: Asset) -> str:
    ext = _asset_extension(asset)
    if ext in TEXT_ROUTE_EXTENSIONS:
        return "TEXT"
    if ext in MULTIMODAL_ROUTE_EXTENSIONS:
        return "MULTIMODAL"
    if asset.asset_type in {"MARKDOWN"}:
        return "TEXT"
    return "MULTIMODAL"


def _build_mismatch_filter(target_model_id: int, embedding_type: str):
    return or_(
        FileLightIndex.file_id.is_(None),
        FileLightIndex.embedding_model_id.is_(None),
        FileLightIndex.embedding_model_id != target_model_id,
        FileLightIndex.index_status != "SUCCEEDED",
    )


def _safe_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _truncate(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    return compact[:limit]


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


def _file_summary(asset: Asset, extracted_text: str) -> str:
    base = extracted_text or asset.snapshot_markdown or asset.content or _asset_file_name(asset)
    return _truncate(base, 1200)


def _build_embedding_inputs(asset: Asset) -> PreparedEmbeddingInput:
    extracted_text, source = _extract_asset_text(asset)
    summary = _file_summary(asset, extracted_text)
    file_name = _asset_file_name(asset)
    ext = _asset_extension(asset)
    route_type = _route_asset(asset)
    text_input = _truncate(f"{file_name}\n\n{extracted_text or summary}", 8000)
    multimodal_payload: dict[str, Any] = {
        "text": _truncate(extracted_text or summary or file_name, 12000),
    }
    file_path = _asset_file_path(asset)
    if route_type == "MULTIMODAL" and file_path and ext in MULTIMODAL_ROUTE_EXTENSIONS:
        media_bytes = file_path.read_bytes()
        encoded = base64.b64encode(media_bytes).decode("ascii")
        media_type = "video" if ext in {"mp4", "mov", "avi", "mkv", "webm", "mpeg", "mpg"} else "image"
        multimodal_payload[media_type] = f"data:{_mime_type_for_extension(ext)};base64,{encoded}"
    return PreparedEmbeddingInput(
        item_id=0,
        file_id=asset.id,
        route_type=route_type,
        content_source=source,
        summary=summary,
        text_input=text_input,
        multimodal_input=multimodal_payload,
    )


def _vector_file_path(task_id: int, file_id: int, embedding_type: str) -> Path:
    return VECTOR_ROOT / f"task_{task_id}" / f"{embedding_type.lower()}_{file_id}.json"


def _write_vector_payload(
    task_id: int,
    file_id: int,
    embedding_type: str,
    payload: dict[str, Any],
) -> str:
    target = _vector_file_path(task_id, file_id, embedding_type)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return os.path.relpath(target, Path.cwd())


def _serialize_task_item(item: EmbeddingRebuildTaskItem) -> dict:
    return {
        "id": item.id,
        "task_id": item.task_id,
        "file_id": item.file_id,
        "route_type": item.route_type,
        "content_source": item.content_source,
        "status": item.status,
        "attempt_count": item.attempt_count,
        "last_error": item.last_error,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
    }


def _refresh_task_counters(db: Session, task: EmbeddingRebuildTask) -> None:
    aggregates = (
        db.query(
            func.count(EmbeddingRebuildTaskItem.id),
            func.sum(case((EmbeddingRebuildTaskItem.status == "SUCCEEDED", 1), else_=0)),
            func.sum(case((EmbeddingRebuildTaskItem.status == "FAILED", 1), else_=0)),
            func.sum(case((EmbeddingRebuildTaskItem.status == "RETRYABLE_FAILED", 1), else_=0)),
        )
        .filter(EmbeddingRebuildTaskItem.task_id == task.id)
        .one()
    )
    discovered = int(aggregates[0] or 0)
    succeeded = int(aggregates[1] or 0)
    failed = int(aggregates[2] or 0)
    retryable_failed = int(aggregates[3] or 0)

    task.discovered_count = discovered
    task.total_count = discovered
    task.succeeded_count = succeeded
    task.failed_count = failed
    task.retryable_failed_count = retryable_failed
    task.processed_count = succeeded + failed
    task.total_batches = math.ceil(discovered / BATCH_SIZE) if discovered > 0 else 0
    task.updated_at = datetime.now()
    task.last_heartbeat_at = datetime.now()


def serialize_rebuild_task(task: EmbeddingRebuildTask) -> dict:
    completed = task.succeeded_count + task.failed_count
    progress = 0.0
    if task.discovered_count > 0:
        progress = min(1.0, completed / task.discovered_count)
    return {
        "id": task.id,
        "embedding_type": task.embedding_type,
        "target_model_id": task.target_model_id,
        "status": task.status,
        "cursor_file_id": task.cursor_file_id,
        "total_count": task.total_count,
        "processed_count": task.processed_count,
        "failed_count": task.failed_count,
        "discovered_count": task.discovered_count,
        "succeeded_count": task.succeeded_count,
        "retryable_failed_count": task.retryable_failed_count,
        "current_batch_no": task.current_batch_no,
        "total_batches": task.total_batches,
        "cancel_requested": task.cancel_requested,
        "progress": round(progress, 4),
        "last_error": task.last_error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "last_heartbeat_at": task.last_heartbeat_at.isoformat() if task.last_heartbeat_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "is_active": task.status in ACTIVE_TASK_STATUSES,
    }


def list_rebuild_tasks(db: Session, limit: int = 20) -> list[dict]:
    rows = (
        db.query(EmbeddingRebuildTask)
        .order_by(EmbeddingRebuildTask.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [serialize_rebuild_task(row) for row in rows]


def list_rebuild_task_items(db: Session, task_id: int, limit: int = 100) -> list[dict]:
    get_rebuild_task(db, task_id)
    rows = (
        db.query(EmbeddingRebuildTaskItem)
        .filter(EmbeddingRebuildTaskItem.task_id == task_id)
        .order_by(EmbeddingRebuildTaskItem.id.asc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [_serialize_task_item(row) for row in rows]


def _find_existing_active_task(
    db: Session,
    embedding_type: str,
    target_model_id: int,
) -> Optional[EmbeddingRebuildTask]:
    return (
        db.query(EmbeddingRebuildTask)
        .filter(
            EmbeddingRebuildTask.embedding_type == embedding_type,
            EmbeddingRebuildTask.target_model_id == target_model_id,
            EmbeddingRebuildTask.status.in_(tuple(ACTIVE_TASK_STATUSES | {"PENDING"})),
        )
        .order_by(EmbeddingRebuildTask.id.desc())
        .first()
    )


def create_rebuild_task(
    db: Session,
    embedding_type: str,
    target_model_id: int,
    trigger_user_id: Optional[int],
) -> EmbeddingRebuildTask:
    existing = _find_existing_active_task(db, embedding_type, target_model_id)
    if existing:
        return existing

    assets = (
        db.query(Asset)
        .outerjoin(
            FileLightIndex,
            and_(
                FileLightIndex.file_id == Asset.id,
                FileLightIndex.embedding_type == embedding_type,
            ),
        )
        .filter(_build_mismatch_filter(target_model_id, embedding_type))
        .order_by(Asset.id.asc())
        .all()
    )
    matched_assets = [asset for asset in assets if _route_asset(asset) == embedding_type]

    task = EmbeddingRebuildTask(
        embedding_type=embedding_type,
        target_model_id=target_model_id,
        trigger_user_id=trigger_user_id,
        status="PENDING",
        cursor_file_id=0,
        total_count=len(matched_assets),
        processed_count=0,
        failed_count=0,
        discovered_count=len(matched_assets),
        succeeded_count=0,
        retryable_failed_count=0,
        current_batch_no=0,
        total_batches=math.ceil(len(matched_assets) / BATCH_SIZE) if matched_assets else 0,
        cancel_requested=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(task)
    db.flush()

    items = [
        EmbeddingRebuildTaskItem(
            task_id=task.id,
            file_id=asset.id,
            route_type=embedding_type,
            status="PENDING",
            attempt_count=0,
            updated_at=datetime.now(),
        )
        for asset in matched_assets
    ]
    if items:
        db.add_all(items)
    db.flush()
    return task


def _needs_rebuild_for_asset(
    db: Session,
    file_id: int,
    embedding_type: str,
    target_model_id: int,
) -> bool:
    row = _get_index_row(db, file_id, embedding_type)
    if not row:
        return True
    if row.embedding_model_id != target_model_id:
        return True
    return row.index_status != "SUCCEEDED"


def create_rebuild_task_for_assets(
    db: Session,
    embedding_type: str,
    target_model_id: int,
    trigger_user_id: Optional[int],
    asset_ids: list[int],
) -> Optional[EmbeddingRebuildTask]:
    if not asset_ids:
        return None

    dedup_ids = sorted({int(asset_id) for asset_id in asset_ids if int(asset_id) > 0})
    if not dedup_ids:
        return None

    assets = (
        db.query(Asset)
        .filter(Asset.id.in_(dedup_ids))
        .order_by(Asset.id.asc())
        .all()
    )

    matched_assets = [
        asset
        for asset in assets
        if _route_asset(asset) == embedding_type
        and _needs_rebuild_for_asset(db, asset.id, embedding_type, target_model_id)
    ]
    if not matched_assets:
        return None

    task = EmbeddingRebuildTask(
        embedding_type=embedding_type,
        target_model_id=target_model_id,
        trigger_user_id=trigger_user_id,
        status="PENDING",
        cursor_file_id=0,
        total_count=len(matched_assets),
        processed_count=0,
        failed_count=0,
        discovered_count=len(matched_assets),
        succeeded_count=0,
        retryable_failed_count=0,
        current_batch_no=0,
        total_batches=math.ceil(len(matched_assets) / BATCH_SIZE) if matched_assets else 0,
        cancel_requested=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(task)
    db.flush()

    items = [
        EmbeddingRebuildTaskItem(
            task_id=task.id,
            file_id=asset.id,
            route_type=embedding_type,
            status="PENDING",
            attempt_count=0,
            updated_at=datetime.now(),
        )
        for asset in matched_assets
    ]
    if items:
        db.add_all(items)
    db.flush()
    return task


def schedule_rebuild_for_asset(
    db: Session,
    asset: Asset,
    trigger_user_id: Optional[int],
) -> list[dict]:
    route_type = _route_asset(asset)
    if route_type == "TEXT":
        target_model_id = _get_config_int(db, TEXT_EMBEDDING_KEY)
        embedding_type = "TEXT"
    else:
        target_model_id = _get_config_int(db, MULTIMODAL_EMBEDDING_KEY)
        embedding_type = "MULTIMODAL"

    if not target_model_id:
        return []

    _validate_embedding_model(db, target_model_id, embedding_type)
    task = create_rebuild_task_for_assets(
        db=db,
        embedding_type=embedding_type,
        target_model_id=target_model_id,
        trigger_user_id=trigger_user_id,
        asset_ids=[asset.id],
    )
    if not task:
        return []
    return [{"task_id": task.id, "embedding_type": embedding_type}]


def update_embedding_config(
    db: Session,
    user_id: int,
    text_model_id: Optional[int],
    multimodal_model_id: Optional[int],
    rebuild_index: bool,
) -> dict:
    _validate_embedding_model(db, text_model_id, "TEXT")
    _validate_embedding_model(db, multimodal_model_id, "MULTIMODAL")

    _set_config_int(db, TEXT_EMBEDDING_KEY, text_model_id, user_id)
    _set_config_int(db, MULTIMODAL_EMBEDDING_KEY, multimodal_model_id, user_id)

    created_tasks: list[dict] = []
    if rebuild_index:
        if text_model_id:
            task = create_rebuild_task(db, "TEXT", text_model_id, user_id)
            created_tasks.append({"task_id": task.id, "embedding_type": "TEXT"})
        if multimodal_model_id:
            task = create_rebuild_task(db, "MULTIMODAL", multimodal_model_id, user_id)
            created_tasks.append({"task_id": task.id, "embedding_type": "MULTIMODAL"})

    db.flush()
    payload = get_embedding_config(db)
    payload["created_rebuild_tasks"] = created_tasks
    return payload


def get_rebuild_task(db: Session, task_id: int) -> EmbeddingRebuildTask:
    task = db.query(EmbeddingRebuildTask).filter(EmbeddingRebuildTask.id == task_id).first()
    if not task:
        raise ValueError("重建任务不存在")
    return task


def mark_task_queued(db: Session, task_id: int) -> dict:
    task = get_rebuild_task(db, task_id)
    if task.status in ACTIVE_TASK_STATUSES:
        return serialize_rebuild_task(task)
    if task.status == "SUCCEEDED":
        raise ValueError("任务已完成，无需再次执行")
    if task.status == "CANCELLED":
        raise ValueError("已取消的任务不能继续执行")
    task.status = "QUEUED"
    task.cancel_requested = False
    task.last_error = None
    task.finished_at = None
    if not task.started_at:
        task.started_at = datetime.now()
    task.updated_at = datetime.now()
    task.last_heartbeat_at = datetime.now()
    db.flush()
    return serialize_rebuild_task(task)


def retry_failed_rebuild_task(db: Session, task_id: int) -> dict:
    task = get_rebuild_task(db, task_id)
    failed_items = (
        db.query(EmbeddingRebuildTaskItem)
        .filter(EmbeddingRebuildTaskItem.task_id == task.id, EmbeddingRebuildTaskItem.status == "FAILED")
        .all()
    )
    for item in failed_items:
        item.status = "PENDING"
        item.attempt_count = 0
        item.last_error = None
        item.finished_at = None
        item.updated_at = datetime.now()
    task.status = "PENDING"
    task.cancel_requested = False
    task.last_error = None
    task.finished_at = None
    _refresh_task_counters(db, task)
    db.flush()
    return serialize_rebuild_task(task)


def request_cancel_rebuild_task(db: Session, task_id: int) -> dict:
    task = get_rebuild_task(db, task_id)
    task.cancel_requested = True
    if task.status == "PENDING":
        task.status = "CANCELLED"
        task.finished_at = datetime.now()
        pending_items = (
            db.query(EmbeddingRebuildTaskItem)
            .filter(
                EmbeddingRebuildTaskItem.task_id == task.id,
                EmbeddingRebuildTaskItem.status.in_(tuple(RETRYABLE_ITEM_STATUSES | {"RUNNING"})),
            )
            .all()
        )
        for item in pending_items:
            item.status = "CANCELLED"
            item.finished_at = datetime.now()
            item.updated_at = datetime.now()
    task.updated_at = datetime.now()
    task.last_heartbeat_at = datetime.now()
    db.flush()
    return serialize_rebuild_task(task)


async def _embed_sub_batch(
    provider,
    model_name: str,
    embedding_type: str,
    payloads: list[PreparedEmbeddingInput],
) -> tuple[dict[int, tuple[list[float], PreparedEmbeddingInput]], dict[int, str]]:
    if not payloads:
        return {}, {}

    try:
        if embedding_type == "MULTIMODAL":
            vectors = await provider.create_multimodal_embeddings(
                model_name,
                [payload.multimodal_input for payload in payloads],
            )
        else:
            vectors = await provider.create_embeddings(model_name, [payload.text_input for payload in payloads])
        if len(vectors) != len(payloads):
            raise RuntimeError("embedding 返回数量与输入数量不一致")
        return ({
            payload.item_id: (vector, payload)
            for payload, vector in zip(payloads, vectors)
        }, {})
    except Exception as batch_exc:
        result: dict[int, tuple[list[float], PreparedEmbeddingInput]] = {}
        errors: dict[int, str] = {}
        for payload in payloads:
            try:
                if embedding_type == "MULTIMODAL":
                    vectors = await provider.create_multimodal_embeddings(model_name, [payload.multimodal_input])
                else:
                    vectors = await provider.create_embeddings(model_name, [payload.text_input])
                vector = vectors[0] if vectors else []
                result[payload.item_id] = (vector, payload)
            except Exception as item_exc:
                errors[payload.item_id] = str(item_exc) or str(batch_exc) or "embedding 生成失败"
        return result, errors


def _get_index_row(db: Session, file_id: int, embedding_type: str) -> Optional[FileLightIndex]:
    return (
        db.query(FileLightIndex)
        .filter(
            FileLightIndex.file_id == file_id,
            FileLightIndex.embedding_type == embedding_type,
        )
        .first()
    )


async def _prepare_batch_inputs(
    items: list[EmbeddingRebuildTaskItem],
    assets_by_id: dict[int, Asset],
) -> list[PreparedEmbeddingInput]:
    prepared: list[PreparedEmbeddingInput] = []
    for item in items:
        asset = assets_by_id.get(item.file_id)
        if not asset:
            continue
        built = await asyncio.to_thread(_build_embedding_inputs, asset)
        built.item_id = item.id
        built.route_type = item.route_type
        prepared.append(built)
    return prepared


def _apply_item_success(
    db: Session,
    task: EmbeddingRebuildTask,
    item: EmbeddingRebuildTaskItem,
    asset: Asset,
    prepared: PreparedEmbeddingInput,
    vector: list[float],
) -> None:
    now = datetime.now()
    vector_ref = _write_vector_payload(
        task.id,
        item.file_id,
        task.embedding_type,
        {
            "task_id": task.id,
            "file_id": item.file_id,
            "embedding_type": task.embedding_type,
            "target_model_id": task.target_model_id,
            "vector": vector,
            "summary": prepared.summary,
            "content_source": prepared.content_source,
            "updated_at": now.isoformat(),
        },
    )

    row = _get_index_row(db, asset.id, task.embedding_type)
    if not row:
        row = FileLightIndex(file_id=asset.id, embedding_type=task.embedding_type)
        db.add(row)

    row.summary = prepared.summary
    row.embedding_type = task.embedding_type
    row.embedding_model_id = task.target_model_id
    row.embedding_dim = len(vector)
    row.vector_ref = vector_ref
    row.index_status = "SUCCEEDED"
    row.retry_count = 0
    row.last_error = None
    row.indexed_at = now
    row.tenant_id = asset.created_by
    row.index_version = (row.index_version or 0) + 1

    item.status = "SUCCEEDED"
    item.content_source = prepared.content_source
    item.last_error = None
    item.finished_at = now
    item.updated_at = now
    task.cursor_file_id = max(task.cursor_file_id, asset.id)


def _apply_item_failure(
    db: Session,
    task: EmbeddingRebuildTask,
    item: EmbeddingRebuildTaskItem,
    asset: Optional[Asset],
    error_message: str,
) -> None:
    now = datetime.now()
    item.last_error = error_message[:1000]
    item.updated_at = now
    item.finished_at = now
    row = _get_index_row(db, item.file_id, task.embedding_type)
    if not row:
        row = FileLightIndex(
            file_id=item.file_id,
            embedding_type=task.embedding_type,
            tenant_id=asset.created_by if asset else None,
        )
        db.add(row)
    row.index_status = "FAILED"
    row.last_error = item.last_error
    row.retry_count = item.attempt_count
    if item.attempt_count >= MAX_ITEM_ATTEMPTS:
        item.status = "FAILED"
    else:
        item.status = "RETRYABLE_FAILED"
    task.last_error = item.last_error
    if asset:
        task.cursor_file_id = max(task.cursor_file_id, asset.id)


def _finalize_task(db: Session, task: EmbeddingRebuildTask) -> None:
    remaining = (
        db.query(EmbeddingRebuildTaskItem)
        .filter(
            EmbeddingRebuildTaskItem.task_id == task.id,
            EmbeddingRebuildTaskItem.status.in_(tuple(RETRYABLE_ITEM_STATUSES | {"RUNNING"})),
        )
        .count()
    )
    failed = (
        db.query(EmbeddingRebuildTaskItem)
        .filter(EmbeddingRebuildTaskItem.task_id == task.id, EmbeddingRebuildTaskItem.status == "FAILED")
        .count()
    )
    now = datetime.now()
    if task.cancel_requested:
        task.status = "CANCELLED"
    elif remaining > 0:
        task.status = "FAILED" if failed > 0 else "PENDING"
    elif failed > 0:
        task.status = "PARTIAL_FAILED"
    else:
        task.status = "SUCCEEDED"
    task.finished_at = now if task.status in TERMINAL_TASK_STATUSES else None
    task.updated_at = now
    task.last_heartbeat_at = now
    _refresh_task_counters(db, task)


async def process_rebuild_task_cycle(task_id: int) -> dict:
    with SessionLocal() as db:
        task = get_rebuild_task(db, task_id)
        if task.cancel_requested:
            pending_items = (
                db.query(EmbeddingRebuildTaskItem)
                .filter(
                    EmbeddingRebuildTaskItem.task_id == task.id,
                    EmbeddingRebuildTaskItem.status.in_(tuple(RETRYABLE_ITEM_STATUSES | {"RUNNING"})),
                )
                .all()
            )
            for item in pending_items:
                item.status = "CANCELLED"
                item.finished_at = datetime.now()
                item.updated_at = datetime.now()
            _finalize_task(db, task)
            db.commit()
            return serialize_rebuild_task(task)

        if task.status in TERMINAL_TASK_STATUSES:
            return serialize_rebuild_task(task)

        task.status = "RUNNING"
        if not task.started_at:
            task.started_at = datetime.now()
        task.updated_at = datetime.now()
        task.last_heartbeat_at = datetime.now()
        task.current_batch_no += 1

        items = (
            db.query(EmbeddingRebuildTaskItem)
            .filter(
                EmbeddingRebuildTaskItem.task_id == task.id,
                EmbeddingRebuildTaskItem.status.in_(tuple(RETRYABLE_ITEM_STATUSES)),
            )
            .order_by(EmbeddingRebuildTaskItem.id.asc())
            .limit(BATCH_SIZE)
            .all()
        )
        if not items:
            _finalize_task(db, task)
            db.commit()
            return serialize_rebuild_task(task)

        asset_ids = [item.file_id for item in items]
        assets = db.query(Asset).filter(Asset.id.in_(asset_ids)).all()
        assets_by_id = {asset.id: asset for asset in assets}
        target_model = (
            db.query(ModelItem)
            .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
            .filter(ModelItem.id == task.target_model_id, ModelProvider.is_enabled == True)
            .first()
        )
        if not target_model:
            raise ValueError("目标模型不存在或已停用")

        for item in items:
            item.status = "RUNNING"
            item.attempt_count += 1
            item.started_at = item.started_at or datetime.now()
            item.updated_at = datetime.now()
        db.commit()

    with SessionLocal() as provider_db:
        target_model = provider_db.query(ModelItem).filter(ModelItem.id == task.target_model_id).first()
        if not target_model:
            raise ValueError("目标模型不存在")
        provider = ProviderFactory.get_provider(target_model.provider_id, provider_db)
        model_name = target_model.model_name

    prepared = await _prepare_batch_inputs(items, assets_by_id)
    chunks = [prepared[i:i + EMBED_SUB_BATCH_SIZE] for i in range(0, len(prepared), EMBED_SUB_BATCH_SIZE)]
    semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)

    async def run_chunk(payloads: list[PreparedEmbeddingInput]):
        async with semaphore:
            return await _embed_sub_batch(provider, model_name, task.embedding_type, payloads)

    chunk_results = await asyncio.gather(*(run_chunk(chunk) for chunk in chunks), return_exceptions=True)
    success_map: dict[int, tuple[list[float], PreparedEmbeddingInput]] = {}
    errors_by_item_id: dict[int, str] = {}
    for payloads, chunk_result in zip(chunks, chunk_results):
        if isinstance(chunk_result, Exception):
            for payload in payloads:
                errors_by_item_id[payload.item_id] = str(chunk_result)
            continue
        chunk_successes, chunk_errors = chunk_result
        success_map.update(chunk_successes)
        errors_by_item_id.update(chunk_errors)

    with SessionLocal() as db:
        task = get_rebuild_task(db, task_id)
        persisted_items = (
            db.query(EmbeddingRebuildTaskItem)
            .filter(EmbeddingRebuildTaskItem.id.in_([item.id for item in items]))
            .all()
        )
        persisted_map = {item.id: item for item in persisted_items}
        persisted_assets = db.query(Asset).filter(Asset.id.in_(asset_ids)).all()
        persisted_assets_map = {asset.id: asset for asset in persisted_assets}

        for original in items:
            item = persisted_map.get(original.id)
            if not item:
                continue
            asset = persisted_assets_map.get(item.file_id)
            if item.id in success_map and asset:
                vector, prepared_payload = success_map[item.id]
                _apply_item_success(db, task, item, asset, prepared_payload, vector)
            else:
                error_message = errors_by_item_id.get(item.id) or "embedding 生成失败"
                _apply_item_failure(db, task, item, asset, error_message)

        _refresh_task_counters(db, task)
        pending_remaining = (
            db.query(EmbeddingRebuildTaskItem)
            .filter(
                EmbeddingRebuildTaskItem.task_id == task.id,
                EmbeddingRebuildTaskItem.status.in_(tuple(RETRYABLE_ITEM_STATUSES)),
            )
            .count()
        )
        if pending_remaining == 0:
            _finalize_task(db, task)
        else:
            task.status = "RUNNING"
            task.updated_at = datetime.now()
            task.last_heartbeat_at = datetime.now()
        db.commit()
        return serialize_rebuild_task(task)
