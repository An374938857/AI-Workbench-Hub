from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.conversation import Conversation
from app.models.model_provider import ModelItem
from app.models.project import Project
from app.models.reference import (
    ConversationReferenceState,
    FileLightIndex,
    ReferenceAuditLog,
    ReferenceScopeSnapshot,
)
from app.models.requirement import Requirement
from app.models.system_config import SystemConfig
from app.models.uploaded_file import UploadedFile
from app.models.workflow import WorkflowInstanceNode, WorkflowNodeConversation
from app.config import get_settings
from app.services.llm.provider_factory import ProviderFactory

TEXT_EMBEDDING_KEY = "global_default_text_embedding_model_id"
MULTIMODAL_EMBEDDING_KEY = "global_default_multimodal_embedding_model_id"
FULL_DOCUMENT_CHAR_BUDGET = 9000
HYBRID_DOCUMENT_CHAR_BUDGET = 18000
CHUNK_SIZE = 900
CHUNK_OVERLAP = 180
SANDBOX_FILE_ID_OFFSET = 1_000_000_000
REFERENCE_MIRROR_ROOT = "references"
logger = logging.getLogger(__name__)
settings = get_settings()


def _safe_text(value: Optional[str], default: str = "") -> str:
    if not value:
        return default
    return value.strip()


def _to_summary(asset: Asset, max_len: int = 600) -> str:
    base = _safe_text(asset.snapshot_markdown) or _safe_text(asset.content)
    if not base:
        return ""
    compact = re.sub(r"\s+", " ", base)
    return compact[:max_len]


def _compact_text(value: Optional[str], max_len: int = 600) -> str:
    base = _safe_text(value)
    if not base:
        return ""
    return re.sub(r"\s+", " ", base)[:max_len]


def _encode_sandbox_file_id(uploaded_file_id: int) -> int:
    return SANDBOX_FILE_ID_OFFSET + int(uploaded_file_id)


def _decode_sandbox_file_id(reference_file_id: int) -> Optional[int]:
    try:
        value = int(reference_file_id)
    except Exception:
        return None
    if value >= SANDBOX_FILE_ID_OFFSET:
        return value - SANDBOX_FILE_ID_OFFSET
    return None


def _source_level(asset: Asset) -> str:
    if asset.scope_type == "PROJECT":
        return "PROJECT_NODE" if asset.node_code else "PROJECT"
    return "REQUIREMENT_NODE" if asset.node_code else "REQUIREMENT"


def _logical_path(asset: Asset) -> str:
    node_part = asset.node_code or "_"
    return f"{asset.scope_type}/{asset.scope_id}/{node_part}"


def _guess_file_size(asset: Asset) -> Optional[int]:
    if not asset.file_ref:
        return None
    file_path = (Path.cwd() / asset.file_ref).resolve()
    if file_path.exists() and file_path.is_file():
        return file_path.stat().st_size
    return None


def _asset_file_name(asset: Asset) -> str:
    if asset.title:
        return asset.title
    if asset.file_ref:
        return os.path.basename(asset.file_ref)
    return f"asset-{asset.id}"


def _scope_title(asset: Asset, db: Session) -> str:
    return _scope_title_by_scope(asset.scope_type, asset.scope_id, db)


def _scope_title_by_scope(scope_type: str, scope_id: int, db: Session) -> str:
    if scope_type == "PROJECT":
        project = db.query(Project).filter(Project.id == scope_id).first()
        return project.name if project and project.name else "未命名项目"

    requirement = db.query(Requirement).filter(Requirement.id == scope_id).first()
    return requirement.title if requirement and requirement.title else "未命名需求"


def _refresh_catalog_scope_titles(db: Session, catalog: list[dict]) -> list[dict]:
    if not catalog:
        return catalog

    project_ids: set[int] = set()
    requirement_ids: set[int] = set()
    for item in catalog:
        scope_type = str(item.get("scope_type") or "").upper()
        scope_id = item.get("scope_id")
        if not isinstance(scope_id, int):
            continue
        if scope_type == "PROJECT":
            project_ids.add(scope_id)
        elif scope_type == "REQUIREMENT":
            requirement_ids.add(scope_id)

    project_name_map: dict[int, str] = {}
    requirement_title_map: dict[int, str] = {}
    if project_ids:
        rows = db.query(Project.id, Project.name).filter(Project.id.in_(project_ids)).all()
        project_name_map = {row[0]: row[1] for row in rows if row[1]}
    if requirement_ids:
        rows = db.query(Requirement.id, Requirement.title).filter(Requirement.id.in_(requirement_ids)).all()
        requirement_title_map = {row[0]: row[1] for row in rows if row[1]}

    for item in catalog:
        scope_type = str(item.get("scope_type") or "").upper()
        scope_id = item.get("scope_id")
        if not isinstance(scope_id, int):
            continue
        if scope_type == "PROJECT":
            item["scope_title"] = project_name_map.get(scope_id) or "未命名项目"
        elif scope_type == "REQUIREMENT":
            item["scope_title"] = requirement_title_map.get(scope_id) or "未命名需求"

    return catalog


def _asset_to_catalog(asset: Asset, db: Session) -> dict:
    file_name = _asset_file_name(asset)
    size = _guess_file_size(asset)
    ext = Path(file_name).suffix.lower().lstrip(".") if file_name else None
    summary = _to_summary(asset)
    return {
        "file_id": asset.id,
        "source_kind": "ASSET",
        "file_name": file_name,
        "logical_path": _logical_path(asset),
        "source_level": _source_level(asset),
        "source_entity_id": asset.scope_id,
        "mime_type": ext,
        "file_size": size,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
        "summary": summary,
        "node_code": asset.node_code,
        "scope_type": asset.scope_type,
        "scope_id": asset.scope_id,
        "scope_title": _scope_title(asset, db),
    }


def _uploaded_file_source_text(file_item: UploadedFile) -> str:
    return _safe_text(file_item.extracted_text)


def _sanitize_rel_path(value: str) -> str:
    normalized = (value or "").replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts)


def _sanitize_filename(value: str, fallback: str) -> str:
    candidate = os.path.basename((value or "").replace("\\", "/")).strip()
    if not candidate:
        candidate = fallback
    candidate = re.sub(r"[<>:\"|?*\x00-\x1f]", "_", candidate).strip(" .")
    return candidate or fallback


def _asset_mirror_rel_path(asset: Asset) -> str:
    scope_type = (asset.scope_type or "ASSET").upper()
    scope_id = int(asset.scope_id or 0)
    node_code = _sanitize_rel_path(asset.node_code or "_") or "_"
    preferred_name = _asset_file_name(asset)
    if "." not in preferred_name:
        preferred_name = f"{preferred_name}.md"
    safe_name = _sanitize_filename(preferred_name, f"asset-{asset.id}.md")
    return (
        f"{REFERENCE_MIRROR_ROOT}/ASSET/{scope_type}/{scope_id}/{node_code}/{safe_name}"
    )


def _sandbox_file_mirror_rel_path(file_item: UploadedFile) -> str:
    source_conv_id = int(file_item.conversation_id or 0)
    sandbox_rel = _sanitize_rel_path(
        file_item.sandbox_path or file_item.original_name or f"file-{file_item.id}.txt"
    )
    if not sandbox_rel:
        sandbox_rel = _sanitize_filename(
            file_item.original_name or "", f"file-{file_item.id}.txt"
        )
    return f"{REFERENCE_MIRROR_ROOT}/CONVERSATION/{source_conv_id}/{sandbox_rel}"


def materialize_references_into_sandbox(
    db: Session,
    conversation: Conversation,
    selected_file_ids: list[int],
) -> dict:
    # 为兼容旧返回结构保留此函数：不执行写盘，仅返回虚拟路径映射。
    selected_ids = sorted(
        {
            int(file_id)
            for file_id in (selected_file_ids or [])
            if str(file_id).isdigit() and int(file_id) > 0
        }
    )
    asset_ids = [file_id for file_id in selected_ids if _decode_sandbox_file_id(file_id) is None]
    sandbox_file_ids = [
        decoded
        for decoded in (_decode_sandbox_file_id(file_id) for file_id in selected_ids)
        if decoded is not None
    ]
    asset_map = {
        asset.id: asset
        for asset in (db.query(Asset).filter(Asset.id.in_(asset_ids)).all() if asset_ids else [])
    }
    sandbox_map = {
        item.id: item
        for item in (
            db.query(UploadedFile).filter(UploadedFile.id.in_(sandbox_file_ids)).all()
            if sandbox_file_ids
            else []
        )
    }
    mounted_paths: list[dict] = []
    for selected_id in selected_ids:
        decoded = _decode_sandbox_file_id(selected_id)
        if decoded is None:
            asset = asset_map.get(selected_id)
            if asset:
                mounted_paths.append({"file_id": selected_id, "sandbox_path": _asset_mirror_rel_path(asset)})
            continue
        file_item = sandbox_map.get(decoded)
        if file_item:
            mounted_paths.append({"file_id": selected_id, "sandbox_path": _sandbox_file_mirror_rel_path(file_item)})
    return {"mounted_count": len(mounted_paths), "mounted_paths": mounted_paths, "warnings": []}


def _uploaded_file_to_catalog(
    file_item: UploadedFile,
    conversation: Conversation,
    node: WorkflowInstanceNode,
    db: Session,
) -> dict:
    conversation_title = conversation.title or ""
    workflow_instance = node.workflow_instance
    instance_scope_type = str(workflow_instance.scope_type or "").upper() if workflow_instance else ""
    instance_scope_id = int(workflow_instance.scope_id) if workflow_instance and workflow_instance.scope_id else 0
    supports_scope_tree = instance_scope_type in {"PROJECT", "REQUIREMENT"} and instance_scope_id > 0
    scope_type = instance_scope_type if supports_scope_tree else "CONVERSATION"
    scope_id = instance_scope_id if supports_scope_tree else conversation.id
    scope_title = (
        _scope_title_by_scope(scope_type, scope_id, db)
        if supports_scope_tree
        else (conversation_title or f"会话 #{conversation.id}")
    )
    sandbox_path = (file_item.sandbox_path or file_item.original_name or "").replace("\\", "/")
    node_code = node.node_code or "_"
    logical_path = f"{scope_type}/{scope_id}/{node_code}/CONVERSATION/{conversation.id}/{sandbox_path}"
    summary = _compact_text(file_item.extracted_text)
    return {
        "file_id": _encode_sandbox_file_id(file_item.id),
        "source_kind": "SANDBOX_FILE",
        "sandbox_file_id": file_item.id,
        "conversation_id": conversation.id,
        "file_name": file_item.original_name,
        "logical_path": logical_path,
        "source_level": "WORKFLOW_CONVERSATION_SANDBOX",
        "source_entity_id": conversation.id,
        "mime_type": file_item.file_type,
        "file_size": file_item.file_size,
        "updated_at": file_item.created_at.isoformat() if file_item.created_at else None,
        "summary": summary,
        "node_code": node.node_code,
        "node_name": node.node_name,
        "conversation_title": conversation_title,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scope_title": scope_title,
    }


def _get_config_int(db: Session, key: str) -> Optional[int]:
    record = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not record or record.value is None:
        return None
    try:
        return int(record.value)
    except Exception:
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _load_vector_ref_payload(vector_ref: Optional[str]) -> Optional[dict]:
    if not vector_ref:
        return None
    path = (Path.cwd() / vector_ref).resolve()
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _pick_primary_index_row(rows: list[FileLightIndex]) -> Optional[FileLightIndex]:
    if not rows:
        return None
    text_row = next((row for row in rows if row.embedding_type == "TEXT"), None)
    if text_row:
        return text_row
    succeeded_row = next((row for row in rows if row.index_status == "SUCCEEDED"), None)
    return succeeded_row or rows[0]


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []
    if len(normalized) <= size:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + size)
        chunks.append(normalized[start:end])
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


async def _create_query_embedding(db: Session, query: str, embedding_type: str) -> list[float]:
    config_key = TEXT_EMBEDDING_KEY if embedding_type == "TEXT" else MULTIMODAL_EMBEDDING_KEY
    model_id = _get_config_int(db, config_key)
    if not model_id:
        return []
    model = db.query(ModelItem).filter(ModelItem.id == model_id).first()
    if not model:
        return []
    provider = ProviderFactory.get_provider(model.provider_id, db)
    if embedding_type == "MULTIMODAL":
        vectors = await provider.create_multimodal_embeddings(
            model.model_name,
            [{"text": query}],
        )
    else:
        vectors = await provider.create_embeddings(model.model_name, [query])
    return vectors[0] if vectors else []


async def _score_catalog_by_vectors(db: Session, catalog: list[dict], query: str) -> dict[int, tuple[float, str]]:
    file_ids = [int(item.get("file_id")) for item in catalog if item.get("file_id")]
    if not file_ids:
        return {}

    text_query_vector = await _create_query_embedding(db, query, "TEXT")
    multi_query_vector = await _create_query_embedding(db, query, "MULTIMODAL")
    rows = db.query(FileLightIndex).filter(FileLightIndex.file_id.in_(file_ids)).all()
    scored: dict[int, tuple[float, str]] = {}
    for row in rows:
        payload = _load_vector_ref_payload(row.vector_ref)
        if not payload:
            continue
        vector = payload.get("vector") or []
        if row.embedding_type == "MULTIMODAL":
            score = _cosine_similarity(multi_query_vector, vector)
            reason = "多模态向量匹配"
        else:
            score = _cosine_similarity(text_query_vector, vector)
            reason = "文本向量匹配"
        if score > 0:
            current = scored.get(row.file_id)
            if current is None or score > current[0]:
                scored[row.file_id] = (score, reason)
    return scored


def get_reference_state(db: Session, conversation_id: int) -> ConversationReferenceState | None:
    return (
        db.query(ConversationReferenceState)
        .filter(ConversationReferenceState.conversation_id == conversation_id)
        .first()
    )


def ensure_reference_state(
    db: Session,
    conversation_id: int,
    user_id: Optional[int] = None,
) -> ConversationReferenceState:
    state = get_reference_state(db, conversation_id)
    if state:
        return state

    state = ConversationReferenceState(
        conversation_id=conversation_id,
        scope_snapshot_id=None,
        selected_file_ids=[],
        empty_mode="none",
        selection_version=0,
        updated_by=user_id,
        updated_at=datetime.now(),
    )
    db.add(state)
    db.flush()
    return state


def _resolve_binding(conversation_id: int, db: Session) -> tuple[str, int, WorkflowInstanceNode | None]:
    bind = (
        db.query(WorkflowNodeConversation)
        .filter(WorkflowNodeConversation.conversation_id == conversation_id)
        .first()
    )
    if not bind:
        return "CONVERSATION", conversation_id, None

    node = (
        db.query(WorkflowInstanceNode)
        .filter(WorkflowInstanceNode.id == bind.workflow_instance_node_id)
        .first()
    )
    if not node:
        return "CONVERSATION", conversation_id, None

    return "WORKFLOW_NODE", node.id, node


def get_conversation_binding_context(db: Session, conversation_id: int) -> dict:
    """Return binding info for reference dialog header display."""
    binding = (
        db.query(WorkflowNodeConversation)
        .filter(WorkflowNodeConversation.conversation_id == conversation_id)
        .first()
    )
    if not binding:
        return {"is_bound": False}

    node = (
        db.query(WorkflowInstanceNode)
        .filter(WorkflowInstanceNode.id == binding.workflow_instance_node_id)
        .first()
    )
    if not node or not node.workflow_instance:
        return {"is_bound": False}

    workflow_instance = node.workflow_instance
    scope_type = str(workflow_instance.scope_type or "").upper()
    scope_id = workflow_instance.scope_id
    scope_title = _scope_title_by_scope(scope_type, scope_id, db) if scope_type in {"PROJECT", "REQUIREMENT"} else ""

    return {
        "is_bound": True,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scope_title": scope_title,
        "node_id": node.id,
        "node_name": node.node_name or node.node_code or f"节点#{node.id}",
    }


def has_workflow_node_binding(conversation_id: int, db: Session) -> bool:
    binding = (
        db.query(WorkflowNodeConversation.id)
        .filter(WorkflowNodeConversation.conversation_id == conversation_id)
        .first()
    )
    return binding is not None


def resolve_scope_snapshot_for_state(
    db: Session,
    conversation: Conversation,
    state: ConversationReferenceState,
) -> int | None:
    """Return effective snapshot id for UI/state read.

    - Unbound conversation: no effective scope snapshot.
    - Bound conversation: build snapshot lazily when missing.
    """
    if not has_workflow_node_binding(conversation.id, db):
        return None

    if state.scope_snapshot_id:
        return state.scope_snapshot_id

    scope_snapshot_id, _ = get_or_build_catalog(conversation, db, force_rebuild=False)
    state.scope_snapshot_id = scope_snapshot_id
    return scope_snapshot_id


def _collect_candidate_assets_for_node(node: WorkflowInstanceNode, db: Session) -> list[Asset]:
    workflow_instance = node.workflow_instance
    if not workflow_instance:
        return []

    scope_type = workflow_instance.scope_type
    scope_id = workflow_instance.scope_id

    query = db.query(Asset)
    if scope_type == "PROJECT":
        return (
            query.filter(Asset.scope_type == "PROJECT", Asset.scope_id == scope_id)
            .order_by(Asset.updated_at.desc(), Asset.id.desc())
            .all()
        )

    # REQUIREMENT：本需求 + 关联项目
    requirement = db.query(Requirement).filter(Requirement.id == scope_id).first()
    project_id = requirement.project_id if requirement else None

    q = query.filter(
        (Asset.scope_type == "REQUIREMENT") & (Asset.scope_id == scope_id)
        | ((Asset.scope_type == "PROJECT") & (Asset.scope_id == project_id))
    )
    return q.order_by(Asset.updated_at.desc(), Asset.id.desc()).all()


def _collect_candidate_sandbox_catalog_for_node(
    node: WorkflowInstanceNode,
    current_user_id: int,
    db: Session,
) -> list[dict]:
    node_items = (
        db.query(WorkflowInstanceNode)
        .filter(WorkflowInstanceNode.workflow_instance_id == node.workflow_instance_id)
        .all()
    )
    if not node_items:
        return []

    node_map = {item.id: item for item in node_items}
    bindings = (
        db.query(WorkflowNodeConversation)
        .filter(WorkflowNodeConversation.workflow_instance_node_id.in_(list(node_map.keys())))
        .all()
    )
    if not bindings:
        return []

    conversation_ids = sorted({item.conversation_id for item in bindings})
    if not conversation_ids:
        return []

    conversations = (
        db.query(Conversation)
        .filter(Conversation.id.in_(conversation_ids), Conversation.user_id == current_user_id)
        .all()
    )
    if not conversations:
        return []

    conversation_map = {item.id: item for item in conversations}
    bind_map = {
        item.conversation_id: item
        for item in bindings
        if item.conversation_id in conversation_map
    }
    if not bind_map:
        return []

    file_items = (
        db.query(UploadedFile)
        .filter(UploadedFile.conversation_id.in_(list(bind_map.keys())))
        .order_by(UploadedFile.created_at.desc(), UploadedFile.id.desc())
        .all()
    )
    catalog: list[dict] = []
    for file_item in file_items:
        bind = bind_map.get(file_item.conversation_id)
        if not bind:
            continue
        bind_node = node_map.get(bind.workflow_instance_node_id)
        conversation = conversation_map.get(file_item.conversation_id)
        if not bind_node or not conversation:
            continue
        catalog.append(_uploaded_file_to_catalog(file_item, conversation, bind_node, db))
    return catalog


def build_scope_snapshot(
    conversation: Conversation,
    db: Session,
) -> tuple[ReferenceScopeSnapshot, list[dict]]:
    binding_type, binding_id, node = _resolve_binding(conversation.id, db)

    catalog: list[dict] = []
    if node:
        assets = _collect_candidate_assets_for_node(node, db)
        catalog.extend([_asset_to_catalog(a, db) for a in assets])
        catalog.extend(_collect_candidate_sandbox_catalog_for_node(node, conversation.user_id, db))

    snapshot = ReferenceScopeSnapshot(
        conversation_id=conversation.id,
        binding_type=binding_type,
        binding_id=binding_id,
        snapshot_json={"all_candidate_files": catalog},
        created_at=datetime.now(),
    )
    db.add(snapshot)
    db.flush()

    state = ensure_reference_state(db, conversation.id, conversation.user_id)
    state.scope_snapshot_id = snapshot.id
    state.updated_at = datetime.now()
    db.flush()

    return snapshot, catalog


def _load_snapshot_catalog(db: Session, snapshot_id: int) -> list[dict]:
    snapshot = (
        db.query(ReferenceScopeSnapshot)
        .filter(ReferenceScopeSnapshot.id == snapshot_id)
        .first()
    )
    if not snapshot:
        return []
    payload = snapshot.snapshot_json or {}
    files = payload.get("all_candidate_files")
    return files if isinstance(files, list) else []


def _query_terms(query: str) -> list[str]:
    tokens = [t for t in re.findall(r"[\w\u4e00-\u9fff]+", query.lower()) if len(t) >= 2]
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


async def recommend_files(
    db: Session,
    query: str,
    catalog: list[dict],
    hard_limit: int = 8,
) -> list[dict]:
    text = _safe_text(query)
    if not text:
        return []

    terms = _query_terms(text)
    vector_scores: dict[int, tuple[float, str]] = {}
    if settings.REFERENCE_RECOMMEND_USE_VECTOR and len(catalog) >= settings.REFERENCE_VECTOR_MIN_CATALOG_SIZE:
        try:
            vector_scores = await _score_catalog_by_vectors(db, catalog, text)
        except Exception:
            logger.exception("引用向量评分失败，降级为关键词匹配")
            vector_scores = {}
    scored: list[tuple[float, dict, list[str], str]] = []
    for item in catalog:
        file_name = str(item.get("file_name") or "")
        summary = str(item.get("summary") or "")
        source_level = str(item.get("source_level") or "")
        logical_path = str(item.get("logical_path") or "")
        scope_title = str(item.get("scope_title") or "")
        merged = f"{file_name} {summary} {source_level} {logical_path} {scope_title}".lower()

        matched_terms: list[str] = []
        score = 0.0
        reason = "与问题语义相关"
        if text.lower() in merged:
            score += 2.0
        for term in terms:
            if term in merged:
                score += 1.0
                matched_terms.append(term)

        vector_hit = vector_scores.get(int(item.get("file_id") or 0))
        if vector_hit:
            score += max(0.0, vector_hit[0]) * 6.0
            reason = vector_hit[1]
        elif matched_terms:
            reason = f"匹配关键词：{', '.join(matched_terms[:3])}"

        if score <= 0:
            continue

        scored.append((score, item, matched_terms, reason))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:hard_limit]

    recommendations: list[dict] = []
    for score, item, matched, reason in top:
        confidence = min(0.98, 0.4 + score * 0.07)
        if matched and reason == "与问题语义相关":
            reason = f"匹配关键词：{', '.join(matched[:3])}"
        recommendations.append(
            {
                "file_id": item.get("file_id"),
                "reason": reason,
                "confidence": round(confidence, 2),
            }
        )
    return recommendations


def get_or_build_catalog(
    conversation: Conversation,
    db: Session,
    force_rebuild: bool = False,
) -> tuple[int, list[dict]]:
    state = ensure_reference_state(db, conversation.id, conversation.user_id)
    should_refresh_for_binding = False
    if state.scope_snapshot_id and has_workflow_node_binding(conversation.id, db):
        snapshot_row = (
            db.query(ReferenceScopeSnapshot.id, ReferenceScopeSnapshot.created_at)
            .filter(ReferenceScopeSnapshot.id == state.scope_snapshot_id)
            .first()
        )
        if snapshot_row and snapshot_row[1]:
            age = datetime.now() - snapshot_row[1]
            should_refresh_for_binding = age > timedelta(seconds=settings.REFERENCE_SCOPE_SNAPSHOT_TTL_SEC)
        else:
            should_refresh_for_binding = True

    if state.scope_snapshot_id and not force_rebuild and not should_refresh_for_binding:
        catalog = _load_snapshot_catalog(db, state.scope_snapshot_id)
        if catalog:
            return state.scope_snapshot_id, _refresh_catalog_scope_titles(db, catalog)

    snapshot, catalog = build_scope_snapshot(conversation, db)
    return snapshot.id, _refresh_catalog_scope_titles(db, catalog)


def confirm_selection(
    db: Session,
    conversation: Conversation,
    selected_file_ids: list[int],
    mode: str,
    user_id: int,
) -> dict:
    if mode not in {"persist_selection", "persist_empty", "turn_only_skip"}:
        raise ValueError("mode 非法")

    state = ensure_reference_state(db, conversation.id, user_id)
    state.updated_by = user_id
    state.updated_at = datetime.now()

    if mode == "persist_selection":
        state.empty_mode = "none"
        state.selected_file_ids = sorted({int(x) for x in selected_file_ids if int(x) > 0})
        state.selection_version += 1
        state.cleared_at = None
    elif mode == "persist_empty":
        state.empty_mode = "sticky"
        state.selected_file_ids = []
        state.selection_version += 1
        state.cleared_at = datetime.now()
    else:
        # turn_only_skip 不改变持久状态
        pass

    db.flush()

    return {
        "selection_version": state.selection_version,
        "reference_state": {
            "conversation_id": state.conversation_id,
            "scope_snapshot_id": state.scope_snapshot_id,
            "selected_file_ids": state.selected_file_ids,
            "empty_mode": state.empty_mode,
        },
    }


def clear_selection(db: Session, conversation: Conversation, user_id: int) -> dict:
    state = ensure_reference_state(db, conversation.id, user_id)
    state.selected_file_ids = []
    state.empty_mode = "none"
    state.selection_version += 1
    state.updated_by = user_id
    state.updated_at = datetime.now()
    state.cleared_at = datetime.now()
    db.flush()

    return {
        "selection_version": state.selection_version,
        "reference_state": {
            "conversation_id": state.conversation_id,
            "scope_snapshot_id": state.scope_snapshot_id,
            "selected_file_ids": [],
            "empty_mode": "none",
        },
    }


@dataclass
class AssembledReferenceContext:
    selected_file_ids: list[int]
    content: Optional[str]
    injected_chunks: list[dict]
    token_usage: dict


def _asset_source_text(asset: Asset) -> str:
    return _safe_text(asset.snapshot_markdown) or _safe_text(asset.content)


async def _score_chunks(
    db: Session,
    query_text: str,
    chunk_records: list[dict],
) -> list[dict]:
    if not query_text or not chunk_records:
        return chunk_records

    text_query_vector = await _create_query_embedding(db, query_text, "TEXT")
    multi_query_vector = await _create_query_embedding(db, query_text, "MULTIMODAL")
    scored: list[dict] = []
    for item in chunk_records:
        payload = item.get("vector_payload") or {}
        vector = payload.get("vector") or []
        embedding_type = str(item.get("embedding_type") or "TEXT")
        query_vector = multi_query_vector if embedding_type == "MULTIMODAL" else text_query_vector
        score = _cosine_similarity(query_vector, vector)
        enriched = dict(item)
        enriched["score"] = score
        scored.append(enriched)
    scored.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return scored


async def assemble_reference_context(
    db: Session,
    conversation_id: int,
    query_text: str = "",
    token_budget: int = 1800,
) -> AssembledReferenceContext:
    state = get_reference_state(db, conversation_id)
    if not state:
        return AssembledReferenceContext([], None, [], {"reference_tokens": 0})

    if state.empty_mode == "sticky":
        return AssembledReferenceContext([], None, [], {"reference_tokens": 0, "mode": "sticky_empty"})

    selected_ids = [int(i) for i in (state.selected_file_ids or []) if isinstance(i, int) or str(i).isdigit()]
    selected_ids = [i for i in selected_ids if i > 0]
    if not selected_ids:
        return AssembledReferenceContext([], None, [], {"reference_tokens": 0})

    asset_ids = [file_id for file_id in selected_ids if _decode_sandbox_file_id(file_id) is None]
    sandbox_file_ids = [
        decoded for decoded in (_decode_sandbox_file_id(file_id) for file_id in selected_ids) if decoded is not None
    ]

    assets = db.query(Asset).filter(Asset.id.in_(asset_ids)).all() if asset_ids else []
    sandbox_files = (
        db.query(UploadedFile).filter(UploadedFile.id.in_(sandbox_file_ids)).all() if sandbox_file_ids else []
    )
    if not assets and not sandbox_files:
        return AssembledReferenceContext([], None, [], {"reference_tokens": 0})

    asset_map = {item.id: item for item in assets}
    sandbox_map = {item.id: item for item in sandbox_files}
    conversation_map: dict[int, Conversation] = {}
    sandbox_conversation_ids = sorted({item.conversation_id for item in sandbox_files})
    if sandbox_conversation_ids:
        conversation_rows = (
            db.query(Conversation)
            .filter(Conversation.id.in_(sandbox_conversation_ids))
            .all()
        )
        conversation_map = {item.id: item for item in conversation_rows}

    selected_entries: list[dict] = []
    for selected_id in selected_ids:
        decoded_sandbox_id = _decode_sandbox_file_id(selected_id)
        if decoded_sandbox_id is None:
            asset = asset_map.get(selected_id)
            if not asset:
                continue
            file_name = _asset_file_name(asset)
            selected_entries.append(
                {
                    "selected_id": selected_id,
                    "asset_id": asset.id,
                    "file_name": file_name,
                    "sandbox_mirror_path": _asset_mirror_rel_path(asset),
                    "source_level": _source_level(asset),
                    "logical_path": _logical_path(asset),
                    "source_text": _asset_source_text(asset),
                    "summary": _to_summary(asset, max_len=800),
                    "file_size": _guess_file_size(asset) or 0,
                }
            )
            continue

        file_item = sandbox_map.get(decoded_sandbox_id)
        if not file_item:
            continue
        conversation = conversation_map.get(file_item.conversation_id)
        title = conversation.title if conversation and conversation.title else f"会话 #{file_item.conversation_id}"
        sandbox_path = (file_item.sandbox_path or file_item.original_name or "").replace("\\", "/")
        selected_entries.append(
            {
                "selected_id": selected_id,
                "asset_id": None,
                "file_name": file_item.original_name,
                "sandbox_mirror_path": _sandbox_file_mirror_rel_path(file_item),
                "source_level": "WORKFLOW_CONVERSATION_SANDBOX",
                "logical_path": f"CONVERSATION/{file_item.conversation_id}/{sandbox_path}",
                "source_text": _uploaded_file_source_text(file_item),
                "summary": _compact_text(file_item.extracted_text, max_len=800),
                "file_size": file_item.file_size or 0,
                "conversation_title": title,
            }
        )

    if not selected_entries:
        return AssembledReferenceContext([], None, [], {"reference_tokens": 0})

    list_budget_chars = int(token_budget * 3 * 0.10)
    summary_budget_chars = int(token_budget * 3 * 0.20)
    chunk_budget_chars = int(token_budget * 3 * 0.70)

    list_lines: list[str] = []
    summary_lines: list[str] = []
    chunk_lines: list[str] = []
    injected_chunks: list[dict] = []

    list_chars = summary_chars = chunk_chars = 0
    source_map: dict[int, str] = {}
    total_chars = 0

    for entry in selected_entries:
        selected_id = int(entry["selected_id"])
        file_name = str(entry["file_name"])
        source_level = str(entry.get("source_level") or "")
        logical_path = str(entry.get("logical_path") or "")
        sandbox_mirror_path = str(entry.get("sandbox_mirror_path") or "")
        item_line = (
            f"- [{selected_id}] {file_name} ({source_level} / {logical_path})"
            f" [sandbox: {sandbox_mirror_path}]"
        )
        if list_chars + len(item_line) <= list_budget_chars:
            list_lines.append(item_line)
            list_chars += len(item_line)

        summary = str(entry.get("summary") or "")
        file_size = int(entry.get("file_size") or 0)
        over_10mb = file_size > 10 * 1024 * 1024
        source_text = str(entry.get("source_text") or "")
        source_map[selected_id] = source_text
        total_chars += len(source_text)

        if summary and summary_chars < summary_budget_chars:
            kept = summary[: max(0, summary_budget_chars - summary_chars)]
            summary_line = f"[{selected_id}] {file_name}: {kept}"
            summary_lines.append(summary_line)
            summary_chars += len(summary_line)
            injected_chunks.append(
                {"file_id": selected_id, "mode": "summary", "chars": len(kept), "over_10mb": over_10mb}
            )

    if total_chars <= FULL_DOCUMENT_CHAR_BUDGET:
        for entry in selected_entries:
            selected_id = int(entry["selected_id"])
            source_text = source_map.get(selected_id) or ""
            if not source_text:
                continue
            file_name = str(entry["file_name"])
            chunk_line = f"[{selected_id}] {file_name}:\n{source_text[:FULL_DOCUMENT_CHAR_BUDGET]}"
            chunk_lines.append(chunk_line)
            chunk_chars += len(chunk_line)
            injected_chunks.append({"file_id": selected_id, "mode": "full_document", "chars": len(source_text)})
        mode = "FULL_DOCUMENT"
    else:
        chunk_candidates: list[dict] = []
        rows = db.query(FileLightIndex).filter(FileLightIndex.file_id.in_(asset_ids)).all() if asset_ids else []
        index_map: dict[int, list[FileLightIndex]] = {}
        for row in rows:
            index_map.setdefault(row.file_id, []).append(row)
        for entry in selected_entries:
            selected_id = int(entry["selected_id"])
            source_text = source_map.get(selected_id) or ""
            if not source_text:
                continue
            asset_id = entry.get("asset_id")
            row = _pick_primary_index_row(index_map.get(asset_id, [])) if asset_id else None
            vector_payload = _load_vector_ref_payload(row.vector_ref) if row else None
            embedding_type = row.embedding_type if row and row.embedding_type else "TEXT"
            for idx, chunk in enumerate(_chunk_text(source_text)):
                chunk_candidates.append(
                    {
                        "file_id": selected_id,
                        "file_name": str(entry["file_name"]),
                        "text": chunk,
                        "embedding_type": embedding_type,
                        "vector_payload": vector_payload,
                        "chunk_index": idx,
                    }
                )

        ranked_chunks = await _score_chunks(db, query_text, chunk_candidates) if chunk_candidates else []
        if total_chars <= HYBRID_DOCUMENT_CHAR_BUDGET and ranked_chunks:
            mode = "HYBRID"
            for entry in selected_entries:
                selected_id = int(entry["selected_id"])
                source_text = source_map.get(selected_id) or ""
                if not source_text:
                    continue
                file_name = str(entry["file_name"])
                excerpt = source_text[: min(len(source_text), 2400)]
                chunk_line = f"[{selected_id}] {file_name}:\n{excerpt}"
                chunk_lines.append(chunk_line)
                chunk_chars += len(chunk_line)
                injected_chunks.append({"file_id": selected_id, "mode": "document_excerpt", "chars": len(excerpt)})
            for item in ranked_chunks[:6]:
                remain = max(0, chunk_budget_chars - chunk_chars)
                if remain <= 0:
                    break
                kept = item["text"][:remain]
                line = f"[{item['file_id']}] {item['file_name']} (高相关片段): {kept}"
                chunk_lines.append(line)
                chunk_chars += len(line)
                injected_chunks.append(
                    {
                        "file_id": item["file_id"],
                        "mode": "vector_chunk",
                        "chars": len(kept),
                        "score": round(float(item.get("score", 0.0)), 4),
                    }
                )
        else:
            mode = "TOPN_CHUNKS"
            for item in ranked_chunks[:10]:
                remain = max(0, chunk_budget_chars - chunk_chars)
                if remain <= 0:
                    break
                kept = item["text"][:remain]
                line = f"[{item['file_id']}] {item['file_name']}: {kept}"
                chunk_lines.append(line)
                chunk_chars += len(line)
                injected_chunks.append(
                    {
                        "file_id": item["file_id"],
                        "mode": "vector_chunk",
                        "chars": len(kept),
                        "score": round(float(item.get("score", 0.0)), 4),
                    }
                )

    if not list_lines and not summary_lines and not chunk_lines:
        return AssembledReferenceContext([int(item["selected_id"]) for item in selected_entries], None, injected_chunks, {"reference_tokens": 0})

    sections = [
        "【引用资料-清单】",
        "\n".join(list_lines) if list_lines else "(无)",
        "\n\n【引用资料-摘要】",
        "\n".join(summary_lines) if summary_lines else "(无)",
        "\n\n【引用资料-片段】",
        "\n".join(chunk_lines) if chunk_lines else "(无)",
        "\n\n请优先依据以上资料回答，并明确标注关键结论来源。",
    ]
    content = "\n".join(sections)
    approx_tokens = max(1, len(content) // 3)

    return AssembledReferenceContext(
        selected_file_ids=[int(item["selected_id"]) for item in selected_entries],
        content=content,
        injected_chunks=injected_chunks,
        token_usage={
            "reference_tokens": approx_tokens,
            "list_chars": list_chars,
            "summary_chars": summary_chars,
            "chunk_chars": chunk_chars,
            "selected_count": len(selected_entries),
            "assembly_mode": mode,
        },
    )


def write_reference_audit(
    db: Session,
    conversation_id: int,
    turn_id: int,
    query_text: str,
    final_selected_ids: list[int],
    injected_chunks: list[dict],
    token_usage: dict,
    recommended_ids: Optional[list[int]] = None,
    tenant_id: Optional[int] = None,
) -> None:
    log = ReferenceAuditLog(
        conversation_id=conversation_id,
        turn_id=turn_id,
        query_text=query_text,
        recommended_ids=recommended_ids,
        final_selected_ids=final_selected_ids,
        injected_chunks=injected_chunks,
        token_usage_json=token_usage,
        tenant_id=tenant_id,
        created_at=datetime.now(),
    )
    db.add(log)


def cleanup_reference_audit_logs(db: Session, retention_days: int = 180) -> int:
    cutoff = datetime.now().timestamp() - retention_days * 24 * 60 * 60
    cutoff_dt = datetime.fromtimestamp(cutoff)
    deleted = (
        db.query(ReferenceAuditLog)
        .filter(ReferenceAuditLog.created_at < cutoff_dt)
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)
