from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.asset import Asset
from app.models.conversation import Conversation
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.models.workflow import WorkflowInstance, WorkflowInstanceNode, WorkflowNodeConversation
from app.schemas.base import ApiResponse
from app.services.sandbox_archive_service import (
    SandboxArchiveMember,
    SandboxArchiveService,
)
from app.services.archive_download_headers import build_archive_download_headers
from app.services.sandbox_archive_naming import (
    sanitize_archive_label,
    wrap_members_with_root,
)

router = APIRouter()


def _asset_to_dict(asset: Asset) -> dict:
    file_type = None
    file_size = None
    if asset.asset_type == "FILE" and asset.file_ref:
        file_type = Path(asset.file_ref).suffix.lower().lstrip(".")
        file_path = (Path.cwd() / asset.file_ref).resolve()
        if file_path.exists() and file_path.is_file():
            file_size = file_path.stat().st_size

    return {
        "id": asset.id,
        "scope_type": asset.scope_type,
        "scope_id": asset.scope_id,
        "node_code": asset.node_code,
        "asset_type": asset.asset_type,
        "title": asset.title,
        "source_url": asset.source_url,
        "file_ref": asset.file_ref,
        "file_type": file_type,
        "file_size": file_size,
        "refetch_status": asset.refetch_status,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _sandbox_file_to_dict(conversation_id: int, file_item: UploadedFile) -> dict:
    return {
        "file_id": file_item.id,
        "original_name": file_item.original_name,
        "file_type": file_item.file_type,
        "file_size": file_item.file_size,
        "sandbox_path": file_item.sandbox_path,
        "created_at": file_item.created_at.isoformat() if file_item.created_at else None,
        "preview_url": f"/api/conversations/{conversation_id}/sandbox/files/{file_item.id}",
        "download_url": f"/api/conversations/{conversation_id}/sandbox/files/{file_item.id}/download",
    }


def _safe_segment(value: str | None, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    cleaned = text.replace("/", "_").replace("\\", "_").strip()
    return cleaned or fallback


def _is_yuque_url(source_url: str | None) -> bool:
    if not source_url:
        return False
    try:
        host = (urlparse(source_url).netloc or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return host == "yuque.com" or host.endswith(".yuque.com") or host == "yuque.cn" or host.endswith(".yuque.cn")


def _asset_display_name(meta: dict) -> str:
    return _safe_segment(
        meta.get("title")
        or meta.get("file_ref")
        or meta.get("source_url")
        or f"{meta.get('asset_type', 'asset')}_{meta.get('id', 'unknown')}",
        f"asset_{meta.get('id', 'unknown')}",
    )


def _resolve_asset_member(asset: Asset, archive_path: str) -> SandboxArchiveMember | None:
    if asset.asset_type == "FILE" and asset.file_ref:
        file_path = (Path.cwd() / asset.file_ref).resolve()
        if file_path.exists() and file_path.is_file():
            return SandboxArchiveMember(archive_path=archive_path, file_path=str(file_path))
        return None

    if asset.asset_type == "MARKDOWN":
        content = asset.content or asset.snapshot_markdown or ""
        target_name = archive_path if archive_path.lower().endswith(".md") else f"{archive_path}.md"
        return SandboxArchiveMember(
            archive_path=target_name,
            content_bytes=content.encode("utf-8"),
        )

    if asset.asset_type in {"URL", "YUQUE_URL"} and _is_yuque_url(asset.source_url):
        if asset.file_ref:
            file_path = (Path.cwd() / asset.file_ref).resolve()
            if file_path.exists() and file_path.is_file():
                target_name = archive_path if archive_path.lower().endswith(".md") else f"{archive_path}.md"
                return SandboxArchiveMember(archive_path=target_name, file_path=str(file_path))
        snapshot = (asset.snapshot_markdown or "").strip()
        if snapshot:
            target_name = archive_path if archive_path.lower().endswith(".md") else f"{archive_path}.md"
            return SandboxArchiveMember(
                archive_path=target_name,
                content_bytes=snapshot.encode("utf-8"),
            )
    return None


def _load_asset_map(db: Session, view_data: dict) -> dict[int, Asset]:
    asset_ids = [int(item["id"]) for item in view_data.get("assets", []) if item.get("id")]
    if not asset_ids:
        return {}
    assets = db.query(Asset).filter(Asset.id.in_(asset_ids)).all()
    return {item.id: item for item in assets}


def _load_sandbox_file_map(db: Session, view_data: dict) -> dict[int, UploadedFile]:
    file_ids: set[int] = set()
    for node in view_data.get("nodes", []):
        for conv in node.get("conversations", []):
            for file_item in conv.get("sandbox_files", []):
                file_id = int(file_item.get("file_id") or 0)
                if file_id > 0:
                    file_ids.add(file_id)
    if not file_ids:
        return {}
    files = db.query(UploadedFile).filter(UploadedFile.id.in_(list(file_ids))).all()
    return {item.id: item for item in files}


def _collect_requirement_archive_members(db: Session, view_data: dict) -> list[SandboxArchiveMember]:
    members: list[SandboxArchiveMember] = []
    asset_map = _load_asset_map(db, view_data)
    file_map = _load_sandbox_file_map(db, view_data)

    for asset_meta in view_data.get("assets", []):
        asset = asset_map.get(int(asset_meta.get("id") or 0))
        if not asset:
            continue
        display_name = _asset_display_name(asset_meta)
        archive_path = f"需求文件/需求级资料/{display_name}"
        member = _resolve_asset_member(asset, archive_path)
        if member:
            members.append(member)

    for node in view_data.get("nodes", []):
        node_name = _safe_segment(node.get("node_name"), f"节点_{node.get('node_id', 'unknown')}")
        for conv in node.get("conversations", []):
            conv_label = _safe_segment(
                f"#{conv.get('conversation_id', '0')} {conv.get('conversation_title') or '未命名会话'}",
                f"会话_{conv.get('conversation_id', '0')}",
            )
            for file_meta in conv.get("sandbox_files", []):
                file_id = int(file_meta.get("file_id") or 0)
                file_record = file_map.get(file_id)
                if not file_record or not file_record.stored_path or not Path(file_record.stored_path).is_file():
                    continue
                filename = _safe_segment(file_meta.get("original_name"), f"file_{file_id}")
                archive_path = f"需求文件/需求关联对话文件/{node_name}/{conv_label}/{filename}"
                members.append(SandboxArchiveMember(archive_path=archive_path, file_path=file_record.stored_path))
    return members


def _collect_project_archive_members(db: Session, view_data: dict) -> list[SandboxArchiveMember]:
    members: list[SandboxArchiveMember] = []
    asset_map = _load_asset_map(db, view_data)
    file_map = _load_sandbox_file_map(db, view_data)

    node_name_map: dict[tuple[str, int, str], str] = {}
    for node in view_data.get("nodes", []):
        scope_type = node.get("instance_scope_type") or "PROJECT"
        scope_id = int(node.get("instance_scope_id") or 0)
        node_code = node.get("node_code") or ""
        node_name_map[(scope_type, scope_id, node_code)] = _safe_segment(
            node.get("node_name"), f"节点_{node_code or node.get('node_id', 'unknown')}"
        )

    for asset_meta in view_data.get("assets", []):
        asset_id = int(asset_meta.get("id") or 0)
        asset = asset_map.get(asset_id)
        if not asset:
            continue
        display_name = _asset_display_name(asset_meta)
        scope_type = asset_meta.get("scope_type")
        node_code = (asset_meta.get("node_code") or "").strip()
        if scope_type == "PROJECT":
            if node_code:
                node_name = node_name_map.get(
                    ("PROJECT", int(asset_meta.get("scope_id") or 0), node_code),
                    _safe_segment(node_code, "未命名节点"),
                )
                archive_path = f"项目级文件/项目级节点会话文件/{node_name}/节点资料/{display_name}"
            else:
                archive_path = f"项目级文件/项目级资料/{display_name}"
        else:
            requirement_title = _safe_segment(asset_meta.get("scope_title"), f"需求_{asset_meta.get('scope_id', 'unknown')}")
            archive_path = f"关联需求文件/{requirement_title}/需求级资料/{display_name}"
        member = _resolve_asset_member(asset, archive_path)
        if member:
            members.append(member)

    aggregated: dict[tuple[str, int, str], dict] = {}
    for node in view_data.get("nodes", []):
        scope_type = node.get("instance_scope_type") or "PROJECT"
        scope_id = int(node.get("instance_scope_id") or 0)
        scope_title = node.get("instance_scope_title") or ("项目级" if scope_type == "PROJECT" else f"需求_{scope_id}")
        node_code = node.get("node_code") or ""
        node_name = _safe_segment(node.get("node_name"), f"节点_{node_code or node.get('node_id', 'unknown')}")
        bucket_key = (scope_type, scope_id, node_code)
        bucket = aggregated.setdefault(
            bucket_key,
            {
                "scope_title": scope_title,
                "node_name": node_name,
                "conversations": defaultdict(list),
            },
        )
        for conv in node.get("conversations", []):
            conv_id = int(conv.get("conversation_id") or 0)
            if conv_id <= 0:
                continue
            bucket["conversations"][(conv_id, conv.get("conversation_title") or "未命名会话")].extend(
                conv.get("sandbox_files", [])
            )

    for (scope_type, scope_id, _node_code), bucket in aggregated.items():
        node_name = _safe_segment(bucket.get("node_name"), "未命名节点")
        if scope_type == "PROJECT":
            base = f"项目级文件/项目级节点会话文件/{node_name}"
        else:
            requirement_title = _safe_segment(bucket.get("scope_title"), f"需求_{scope_id}")
            base = f"关联需求文件/{requirement_title}/需求关联对话文件/{node_name}"

        for (conv_id, conv_title), file_metas in bucket["conversations"].items():
            conv_label = _safe_segment(f"#{conv_id} {conv_title}", f"会话_{conv_id}")
            seen_file_ids: set[int] = set()
            for file_meta in file_metas:
                file_id = int(file_meta.get("file_id") or 0)
                if file_id <= 0 or file_id in seen_file_ids:
                    continue
                seen_file_ids.add(file_id)
                file_record = file_map.get(file_id)
                if not file_record or not file_record.stored_path or not Path(file_record.stored_path).is_file():
                    continue
                filename = _safe_segment(file_meta.get("original_name"), f"file_{file_id}")
                members.append(
                    SandboxArchiveMember(
                        archive_path=f"{base}/{conv_label}/{filename}",
                        file_path=file_record.stored_path,
                    )
                )
    return members


def _load_scope_graph(
    db: Session,
    scope_type: str,
    scope_id: int,
    current_user_id: int,
) -> dict:
    instance_query = db.query(WorkflowInstance)
    scope_name: str
    if scope_type == "PROJECT":
        scope_name = db.query(Project.name).filter(Project.id == scope_id).scalar() or f"项目_{scope_id}"
    else:
        scope_name = db.query(Requirement.title).filter(Requirement.id == scope_id).scalar() or f"需求_{scope_id}"

    requirement_ids: list[int] = []
    requirement_title_map: dict[int, str] = {}
    if scope_type == "PROJECT":
        requirement_items = (
            db.query(Requirement.id, Requirement.title)
            .filter(Requirement.project_id == scope_id)
            .all()
        )
        requirement_ids = [item.id for item in requirement_items]
        requirement_title_map = {item.id: item.title for item in requirement_items}
        project_instances = (
            instance_query
            .filter(
                WorkflowInstance.scope_type == "PROJECT",
                WorkflowInstance.scope_id == scope_id,
            )
            .all()
        )
        requirement_instances = []
        if requirement_ids:
            requirement_instances = (
                instance_query
                .filter(
                    WorkflowInstance.scope_type == "REQUIREMENT",
                    WorkflowInstance.scope_id.in_(requirement_ids),
                )
                .all()
            )
        instances = project_instances + requirement_instances
    else:
        requirement_item = (
            db.query(Requirement.id, Requirement.title)
            .filter(Requirement.id == scope_id)
            .first()
        )
        if requirement_item:
            requirement_title_map[requirement_item.id] = requirement_item.title
        instances = (
            instance_query
            .filter(
                WorkflowInstance.scope_type == "REQUIREMENT",
                WorkflowInstance.scope_id == scope_id,
            )
            .all()
        )

    if scope_type == "PROJECT":
        asset_filters = [
            (Asset.scope_type == "PROJECT") & (Asset.scope_id == scope_id),
        ]
        if requirement_ids:
            asset_filters.append(
                (Asset.scope_type == "REQUIREMENT") & (Asset.scope_id.in_(requirement_ids))
            )
        assets = (
            db.query(Asset)
            .filter(or_(*asset_filters))
            .order_by(Asset.id.desc())
            .all()
        )
    else:
        assets = (
            db.query(Asset)
            .filter(
                Asset.scope_type == scope_type,
                Asset.scope_id == scope_id,
            )
            .order_by(Asset.id.desc())
            .all()
        )

    asset_payload = []
    for item in assets:
        payload = _asset_to_dict(item)
        if item.scope_type == "REQUIREMENT":
            payload["scope_title"] = requirement_title_map.get(item.scope_id, f"需求 #{item.scope_id}")
        elif item.scope_type == "PROJECT":
            payload["scope_title"] = "项目级"
        asset_payload.append(payload)

    requirement_count = len(requirement_ids) if scope_type == "PROJECT" else 1

    instance_ids = [item.id for item in instances]
    instance_scope_map = {
        item.id: {
            "scope_type": item.scope_type,
            "scope_id": item.scope_id,
            "scope_title": (
                requirement_title_map.get(item.scope_id, f"需求 #{item.scope_id}")
                if item.scope_type == "REQUIREMENT"
                else "项目级"
            ),
        }
        for item in instances
    }
    if not instance_ids:
        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope_name": scope_name,
            "assets": asset_payload,
            "nodes": [],
            "summary": {
                "asset_count": len(assets),
                "node_count": 0,
                "conversation_count": 0,
                "sandbox_file_count": 0,
                "requirement_count": requirement_count,
            },
        }

    nodes = (
        db.query(WorkflowInstanceNode)
        .filter(WorkflowInstanceNode.workflow_instance_id.in_(instance_ids))
        .order_by(WorkflowInstanceNode.workflow_instance_id.asc(), WorkflowInstanceNode.node_order.asc())
        .all()
    )
    node_ids = [item.id for item in nodes]

    bindings = []
    if node_ids:
        bindings = (
            db.query(WorkflowNodeConversation)
            .filter(WorkflowNodeConversation.workflow_instance_node_id.in_(node_ids))
            .all()
        )

    conversation_ids = sorted({item.conversation_id for item in bindings})
    conversations = {}
    sandbox_files = {}
    if conversation_ids:
        conversation_items = (
            db.query(Conversation)
            .filter(
                Conversation.id.in_(conversation_ids),
                Conversation.user_id == current_user_id,
            )
            .all()
        )
        conversations = {item.id: item for item in conversation_items}

        sandbox_items = (
            db.query(UploadedFile)
            .filter(UploadedFile.conversation_id.in_(list(conversations.keys())))
            .order_by(UploadedFile.conversation_id.asc(), UploadedFile.created_at.desc())
            .all()
        )
        for file_item in sandbox_items:
            sandbox_files.setdefault(file_item.conversation_id, []).append(file_item)

    binding_map: dict[int, list[WorkflowNodeConversation]] = {}
    for item in bindings:
        binding_map.setdefault(item.workflow_instance_node_id, []).append(item)

    node_payload = []
    conversation_counter = 0
    file_counter = 0
    for node in nodes:
        instance_scope = instance_scope_map.get(node.workflow_instance_id, {})
        node_conversations = []
        for binding in binding_map.get(node.id, []):
            conv = conversations.get(binding.conversation_id)
            if not conv:
                continue
            files = [_sandbox_file_to_dict(conv.id, file_item) for file_item in sandbox_files.get(conv.id, [])]
            conversation_counter += 1
            file_counter += len(files)
            node_conversations.append(
                {
                    "conversation_id": conv.id,
                    "conversation_title": conv.title,
                    "binding_type": binding.binding_type,
                    "scope_type": instance_scope.get("scope_type", "PROJECT"),
                    "scope_id": instance_scope.get("scope_id"),
                    "scope_title": instance_scope.get("scope_title", "项目级"),
                    "sandbox_files": files,
                }
            )

        node_payload.append(
            {
                "instance_id": node.workflow_instance_id,
                "node_id": node.id,
                "node_code": node.node_code,
                "node_name": node.node_name,
                "node_order": node.node_order,
                "status": node.status,
                "instance_scope_type": instance_scope.get("scope_type", "PROJECT"),
                "instance_scope_id": instance_scope.get("scope_id"),
                "instance_scope_title": instance_scope.get("scope_title", "项目级"),
                "conversations": node_conversations,
            }
        )

    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scope_name": scope_name,
        "assets": asset_payload,
        "nodes": node_payload,
        "summary": {
            "asset_count": len(assets),
            "node_count": len(node_payload),
            "conversation_count": conversation_counter,
            "sandbox_file_count": file_counter,
            "requirement_count": requirement_count,
        },
    }


@router.get("/project/{project_id}")
def get_project_sandbox_view(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if project_id <= 0:
        return ApiResponse.error(40001, "project_id 必须为正整数")
    data = _load_scope_graph(
        db=db,
        scope_type="PROJECT",
        scope_id=project_id,
        current_user_id=current_user.id,
    )
    return ApiResponse.success(data=data)


@router.get("/requirement/{requirement_id}")
def get_requirement_sandbox_view(
    requirement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if requirement_id <= 0:
        return ApiResponse.error(40001, "requirement_id 必须为正整数")
    data = _load_scope_graph(
        db=db,
        scope_type="REQUIREMENT",
        scope_id=requirement_id,
        current_user_id=current_user.id,
    )
    return ApiResponse.success(data=data)


@router.get("/project/{project_id}/archive/download")
def download_project_sandbox_archive(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if project_id <= 0:
        return ApiResponse.error(40001, "project_id 必须为正整数")

    view_data = _load_scope_graph(
        db=db,
        scope_type="PROJECT",
        scope_id=project_id,
        current_user_id=current_user.id,
    )
    members = _collect_project_archive_members(db, view_data)
    if not members:
        return ApiResponse.error(40401, "当前项目沙箱没有可打包文件")

    project_name = db.query(Project.name).filter(Project.id == project_id).scalar()
    archive_label = sanitize_archive_label(project_name, fallback=f"project_{project_id}")
    wrapped_members = wrap_members_with_root(members, archive_label)
    archive_filename = f"{archive_label}.zip"

    archive_service = SandboxArchiveService()
    archive_path = archive_service.create_archive(
        members=wrapped_members,
        archive_filename=archive_filename,
    )
    return FileResponse(
        archive_path,
        filename=archive_filename,
        headers=build_archive_download_headers(archive_filename),
        media_type="application/zip",
        background=BackgroundTask(SandboxArchiveService.cleanup_file, archive_path),
    )


@router.get("/requirement/{requirement_id}/archive/download")
def download_requirement_sandbox_archive(
    requirement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if requirement_id <= 0:
        return ApiResponse.error(40001, "requirement_id 必须为正整数")

    view_data = _load_scope_graph(
        db=db,
        scope_type="REQUIREMENT",
        scope_id=requirement_id,
        current_user_id=current_user.id,
    )
    members = _collect_requirement_archive_members(db, view_data)
    if not members:
        return ApiResponse.error(40401, "当前需求沙箱没有可打包文件")

    requirement_title = db.query(Requirement.title).filter(Requirement.id == requirement_id).scalar()
    archive_label = sanitize_archive_label(requirement_title, fallback=f"requirement_{requirement_id}")
    wrapped_members = wrap_members_with_root(members, archive_label)
    archive_filename = f"{archive_label}.zip"

    archive_service = SandboxArchiveService()
    archive_path = archive_service.create_archive(
        members=wrapped_members,
        archive_filename=archive_filename,
    )
    return FileResponse(
        archive_path,
        filename=archive_filename,
        headers=build_archive_download_headers(archive_filename),
        media_type="application/zip",
        background=BackgroundTask(SandboxArchiveService.cleanup_file, archive_path),
    )
