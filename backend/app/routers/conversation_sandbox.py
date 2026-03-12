import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.conversation import Conversation
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.file_preview_service import build_preview_payload
from app.services.archive_download_headers import build_archive_download_headers
from app.services.sandbox_archive_service import (
    SandboxArchiveMember,
    SandboxArchiveService,
)
from app.services.sandbox_archive_naming import (
    sanitize_archive_label,
    wrap_members_with_root,
)
from app.services.sandbox_file_manager import SandboxFileManager
from app.services.sandbox_change_counter import (
    increase_sandbox_unread_change_count,
    reset_sandbox_unread_change_count,
)
from app.services.conversation_events import get_conversation_event_bus
from app.routers.conversations_shared import get_owned_conversation_or_error

logger = logging.getLogger(__name__)
router = APIRouter()


class SandboxFileRenameRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=255)


class SandboxFileContentUpdateRequest(BaseModel):
    content: str = Field(default="")


def _is_markdown_file(file_record: UploadedFile) -> bool:
    file_type = (file_record.file_type or "").lower()
    if file_type in {"md", "markdown"}:
        return True
    filename = (file_record.original_name or "").lower()
    return filename.endswith(".md") or filename.endswith(".markdown")


@router.get("/{conversation_id}/sandbox/files", response_model=ApiResponse)
def get_sandbox_files(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_manager = SandboxFileManager()
    reconcile_result = file_manager.reconcile_sandbox_files(
        conversation_id, current_user.id, db
    )
    if not reconcile_result["success"]:
        return ApiResponse.error(500, reconcile_result["message"])

    file_items = []
    for f in reconcile_result["files"]:
        file_items.append(
            {
                "file_id": f["file_id"],
                "filename": f["filename"],
                "original_name": f["original_name"],
                "file_size": f["file_size"],
                "file_type": f["file_type"],
                "source": f["source"],
                "sandbox_path": f["sandbox_path"],
                "created_at": f["created_at"],
            }
        )

    sandbox_size = file_manager.get_sandbox_size(conversation_id)
    sandbox_size_mb = sandbox_size / 1024 / 1024
    sandbox_size_limit_mb = 100

    response_data = {
        "files": file_items,
        "total": len(file_items),
        "total_size": reconcile_result["total_size"],
        "sandbox_size_mb": round(sandbox_size_mb, 2),
        "sandbox_size_limit_mb": sandbox_size_limit_mb,
    }

    return ApiResponse.success(data=response_data)


@router.get("/{conversation_id}/sandbox/files/{file_id}", response_model=ApiResponse)
def get_sandbox_file(
    conversation_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_record = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == file_id, UploadedFile.conversation_id == conversation_id
        )
        .first()
    )
    if not file_record:
        return ApiResponse.error(404, "文件不存在")

    if not os.path.exists(file_record.stored_path):
        return ApiResponse.error(404, "文件不存在于磁盘")
    download_url = f"/api/conversations/{conversation_id}/sandbox/files/{file_id}/download"
    payload = build_preview_payload(
        file_path=file_record.stored_path,
        file_type=file_record.file_type,
        filename=file_record.original_name,
        file_size=file_record.file_size,
        download_url=download_url,
        image_preview_url=f"/api/files/image/{file_id}",
    )
    payload["file_id"] = file_record.id
    payload["can_edit"] = _is_markdown_file(file_record)
    return ApiResponse.success(data=payload)


@router.get("/{conversation_id}/sandbox/files/{file_id}/download")
def download_sandbox_file(
    conversation_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_record = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == file_id, UploadedFile.conversation_id == conversation_id
        )
        .first()
    )
    if not file_record:
        return ApiResponse.error(404, "文件不存在")

    if not os.path.exists(file_record.stored_path):
        return ApiResponse.error(404, "文件不存在于磁盘")

    return FileResponse(
        file_record.stored_path,
        filename=file_record.original_name,
        media_type="application/octet-stream",
    )


@router.delete("/{conversation_id}/sandbox/files/{file_id}", response_model=ApiResponse)
def delete_sandbox_file(
    conversation_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_record = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == file_id, UploadedFile.conversation_id == conversation_id
        )
        .first()
    )
    if not file_record:
        return ApiResponse.error(404, "文件不存在")

    if os.path.exists(file_record.stored_path):
        try:
            os.remove(file_record.stored_path)
        except Exception as e:
            logger.error(f"删除文件失败: {e}")

    db.delete(file_record)
    increase_sandbox_unread_change_count(db, conversation_id, delta=1)
    db.commit()

    return ApiResponse.success(data={"message": "文件删除成功"})


@router.put("/{conversation_id}/sandbox/files/{file_id}/rename", response_model=ApiResponse)
def rename_sandbox_file(
    conversation_id: int,
    file_id: int,
    body: SandboxFileRenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_record = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == file_id,
            UploadedFile.conversation_id == conversation_id,
        )
        .first()
    )
    if not file_record:
        return ApiResponse.error(404, "文件不存在")

    new_name = body.new_name.strip()
    if not new_name:
        return ApiResponse.error(400, "新文件名不能为空")
    if "/" in new_name or "\\" in new_name:
        return ApiResponse.error(400, "文件名不能包含路径分隔符")
    if new_name in {".", ".."}:
        return ApiResponse.error(400, "文件名不合法")
    if new_name == file_record.original_name:
        return ApiResponse.success(data={"message": "文件名未变更"})

    old_path = Path(file_record.stored_path)
    if not old_path.exists() or not old_path.is_file():
        return ApiResponse.error(404, "文件不存在于磁盘")

    new_path = old_path.with_name(new_name)
    if new_path.exists():
        return ApiResponse.error(400, "目标文件名已存在")

    try:
        old_path.rename(new_path)
    except Exception as exc:
        logger.error("重命名沙箱文件失败: %s", exc)
        return ApiResponse.error(500, "重命名失败，请稍后重试")

    file_record.stored_path = str(new_path)
    file_record.original_name = new_name
    if file_record.sandbox_path:
        old_sandbox_path = file_record.sandbox_path.replace("\\", "/")
        parent_path = old_sandbox_path.rsplit("/", 1)[0] if "/" in old_sandbox_path else ""
        file_record.sandbox_path = f"{parent_path}/{new_name}" if parent_path else new_name

    if "." in new_name:
        file_record.file_type = new_name.rsplit(".", 1)[-1].lower()

    increase_sandbox_unread_change_count(db, conversation_id, delta=1)
    db.commit()

    return ApiResponse.success(
        data={
            "file_id": file_record.id,
            "original_name": file_record.original_name,
            "sandbox_path": file_record.sandbox_path,
        },
        message="文件重命名成功",
    )


@router.put("/{conversation_id}/sandbox/files/{file_id}/content", response_model=ApiResponse)
def update_sandbox_file_content(
    conversation_id: int,
    file_id: int,
    body: SandboxFileContentUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_record = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == file_id,
            UploadedFile.conversation_id == conversation_id,
        )
        .first()
    )
    if not file_record:
        return ApiResponse.error(404, "文件不存在")

    if not _is_markdown_file(file_record):
        return ApiResponse.error(400, "仅支持编辑 Markdown 文件")

    target_path = Path(file_record.stored_path)
    if not target_path.exists() or not target_path.is_file():
        return ApiResponse.error(404, "文件不存在于磁盘")

    content = body.content or ""
    try:
        target_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.error("更新沙箱 Markdown 文件失败: %s", exc, exc_info=True)
        return ApiResponse.error(500, "保存失败，请稍后重试")

    file_record.file_size = len(content.encode("utf-8"))
    file_record.extracted_text = content
    if (file_record.file_type or "").lower() not in {"md", "markdown"}:
        file_record.file_type = "md"

    increase_sandbox_unread_change_count(db, conversation_id, delta=1)
    db.commit()
    db.refresh(file_record)

    return ApiResponse.success(
        data={
            "file_id": file_record.id,
            "file_size": file_record.file_size,
            "file_type": file_record.file_type,
            "content": content,
        },
        message="文件保存成功",
    )


@router.delete("/{conversation_id}/sandbox/directories", response_model=ApiResponse)
def delete_sandbox_directory(
    conversation_id: int,
    path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_manager = SandboxFileManager()
    result = file_manager.delete_directory(conversation_id, path)
    if not result["success"]:
        return ApiResponse.error(400, result["message"])

    normalized_path = os.path.normpath(path).replace("\\", "/")
    file_records = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.conversation_id == conversation_id,
            or_(
                UploadedFile.sandbox_path == normalized_path,
                UploadedFile.sandbox_path.like(f"{normalized_path}/%"),
            ),
        )
        .all()
    )

    for file_record in file_records:
        db.delete(file_record)
    if file_records:
        increase_sandbox_unread_change_count(db, conversation_id, delta=len(file_records))
    db.commit()

    return ApiResponse.success(
        data={
            "message": "目录删除成功",
            "deleted_count": len(file_records),
            "path": normalized_path,
        }
    )


@router.get("/{conversation_id}/sandbox/archive/download")
def download_sandbox_archive(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_records = (
        db.query(UploadedFile)
        .filter(UploadedFile.conversation_id == conversation_id)
        .order_by(UploadedFile.created_at.asc(), UploadedFile.id.asc())
        .all()
    )

    members: list[SandboxArchiveMember] = []
    for record in file_records:
        if not record.stored_path or not os.path.isfile(record.stored_path):
            continue
        archive_path = (record.sandbox_path or record.original_name or f"file_{record.id}").strip()
        if not archive_path:
            archive_path = f"file_{record.id}"
        members.append(
            SandboxArchiveMember(
                archive_path=archive_path,
                file_path=record.stored_path,
            )
        )

    if not members:
        return ApiResponse.error(404, "沙箱中没有可打包的文件")

    archive_label = sanitize_archive_label(
        conversation.title if conversation else None,
        fallback=f"conversation_{conversation_id}",
    )
    wrapped_members = wrap_members_with_root(members, archive_label)
    archive_filename = f"{archive_label}.zip"

    archive_service = SandboxArchiveService()
    archive_path = archive_service.create_archive(
        wrapped_members,
        archive_filename=archive_filename,
    )
    return FileResponse(
        archive_path,
        filename=archive_filename,
        headers=build_archive_download_headers(archive_filename),
        media_type="application/zip",
        background=BackgroundTask(SandboxArchiveService.cleanup_file, archive_path),
    )


@router.post("/{conversation_id}/sandbox/cleanup", response_model=ApiResponse)
def cleanup_sandbox(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv, error = get_owned_conversation_or_error(conversation_id, current_user.id, db, 404, "对话不存在")
    if error:
        return error

    file_manager = SandboxFileManager()
    file_record_count = (
        db.query(UploadedFile)
        .filter(UploadedFile.conversation_id == conversation_id)
        .count()
    )
    result = file_manager.cleanup_sandbox(conversation_id)

    conv.sandbox_cleaned = True
    if result["success"] and (result.get("freed_size", 0) > 0 or file_record_count > 0):
        increase_sandbox_unread_change_count(
            db,
            conversation_id,
            delta=max(file_record_count, 1),
        )
    db.commit()
    db.refresh(conv)
    get_conversation_event_bus().publish_conversation_snapshot_nowait(
        conv=conv,
        event_type="conversation.updated",
    )

    response_data = {
        "success": result["success"],
        "message": result["message"],
        "freed_size": result["freed_size"],
        "freed_size_mb": round(result["freed_size"] / 1024 / 1024, 2),
    }

    return ApiResponse.success(data=response_data)


@router.post("/{conversation_id}/sandbox/changes/read", response_model=ApiResponse)
def mark_sandbox_changes_read(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv, error = get_owned_conversation_or_error(
        conversation_id,
        current_user.id,
        db,
        404,
        "对话不存在",
    )
    if error:
        return error

    unread_before = (
        db.query(Conversation.sandbox_unread_change_count)
        .filter(Conversation.id == conversation_id)
        .scalar()
    ) or 0
    reset_sandbox_unread_change_count(db, conversation_id)
    db.commit()
    db.refresh(conv)
    get_conversation_event_bus().publish_conversation_snapshot_nowait(
        conv=conv,
        event_type="conversation.updated",
    )

    return ApiResponse.success(
        data={
            "conversation_id": conversation_id,
            "unread_before": int(unread_before),
            "unread_after": 0,
        }
    )
