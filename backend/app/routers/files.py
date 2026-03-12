import os
import logging
import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db, get_current_user
from app.models.uploaded_file import UploadedFile as UploadedFileModel
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.file_service import extract_text
from app.services.sandbox_file_manager import SandboxFileManager
from app.services.sandbox_change_counter import increase_sandbox_unread_change_count

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

IMAGE_TYPES = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}
TEXT_TYPES = {"txt", "md", "csv"}
BINARY_DOC_TYPES = {"docx", "xlsx", "pdf"}
ALLOWED_TYPES = TEXT_TYPES | BINARY_DOC_TYPES | IMAGE_TYPES

# 沙箱文件管理器
sandbox_manager = SandboxFileManager()


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await _do_upload(file, conversation_id, db, current_user)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return ApiResponse.error(50000, f"上传失败: {str(e)[:200]}")


async def _do_upload(
    file: UploadFile,
    conversation_id: int,
    db: Session,
    current_user: User,
):
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ALLOWED_TYPES:
        return ApiResponse.error(40100, f"不支持的文件格式，仅支持 {', '.join(sorted(ALLOWED_TYPES))}")

    content = await file.read()

    # PDF 基本格式校验，避免将 HTML/文本误传为 .pdf
    if ext == "pdf" and b"%PDF" not in content[:1024]:
        head_bytes = content[:64]
        logger.warning(
            "PDF 头校验失败: filename=%s content_type=%s size=%s head_hex=%s head_text=%s",
            filename,
            file.content_type,
            len(content),
            head_bytes.hex(),
            head_bytes.decode("utf-8", errors="replace").replace("\n", "\\n"),
        )
        return ApiResponse.error(40100, "文件扩展名为 .pdf，但内容不是有效 PDF 文件")

    # 存储到沙箱
    subdir = "uploads"
    sandbox_path = os.path.join(subdir, filename)

    # 初始化沙箱
    sandbox_manager.init_sandbox(conversation_id)

    # 根据文件类型选择写入方式（二进制文件不能走文本 decode）
    # 额外防御：即使分类配置错误，只要内容是 Office ZIP 头也强制按二进制写入
    is_image = ext in IMAGE_TYPES
    is_binary_doc = ext in BINARY_DOC_TYPES or (
        ext in {"docx", "xlsx"} and content.startswith(b"PK\x03\x04")
    )
    if is_image or is_binary_doc:
        # 图片/PDF/Office 文档使用二进制写入
        result = sandbox_manager.create_file_binary(
            conversation_id=conversation_id,
            filename=filename,
            content=content,
            subdir=subdir,
            overwrite=False
        )
    else:
        # 纯文本文件使用文本写入
        if b"\x00" in content[:4096]:
            return ApiResponse.error(40100, "文件内容疑似二进制，请检查文件格式后重试")
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content.decode("latin-1")
        result = sandbox_manager.create_file(
            conversation_id=conversation_id,
            filename=filename,
            content=text_content,
            subdir=subdir,
            overwrite=False
        )

    if not result["success"]:
        return ApiResponse.error(40103, result["message"])

    stored_path = result["path"]
    logger.info(
        "文件上传写入完成: conversation_id=%s, filename=%s, ext=%s, size=%s, binary=%s",
        conversation_id,
        filename,
        ext,
        len(content),
        is_image or is_binary_doc,
    )

    is_image = ext in IMAGE_TYPES
    extracted = None
    if not is_image:
        try:
            extracted = extract_text(stored_path, ext)
        except Exception as e:
            extracted = f"[文件内容提取失败: {str(e)[:100]}]"

    record = UploadedFileModel(
        conversation_id=conversation_id,
        user_id=current_user.id,
        original_name=filename,
        stored_path=stored_path,
        file_size=len(content),
        file_type=ext,
        extracted_text=extracted,
        source="upload",
        sandbox_path=sandbox_path,
    )
    db.add(record)
    increase_sandbox_unread_change_count(db, conversation_id, delta=1)
    db.commit()
    db.refresh(record)

    preview = (extracted[:300] if extracted else "") if not is_image else ""

    return ApiResponse.success(data={
        "file_id": record.id,
        "original_name": record.original_name,
        "file_type": record.file_type,
        "file_size": record.file_size,
        "is_image": is_image,
        "image_url": f"/api/files/image/{record.id}" if is_image else None,
        "extracted_text_preview": preview,
    })


@router.get("/image/{file_id}")
def get_image(file_id: int, db: Session = Depends(get_db)):
    """返回图片文件内容（无鉴权，供 LLM API 和前端直接访问）"""
    record = db.query(UploadedFileModel).filter(UploadedFileModel.id == file_id).first()
    normalized_type = (record.file_type or "").lower() if record else ""
    if not record or normalized_type not in IMAGE_TYPES:
        raise HTTPException(status_code=404, detail="图片不存在")
    if not os.path.isfile(record.stored_path):
        raise HTTPException(status_code=404, detail="图片文件丢失")

    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}
    media_type = mime_map.get(normalized_type, f"image/{normalized_type}")
    return FileResponse(record.stored_path, media_type=media_type)


@router.get("/icons/{filename}")
def get_icon(filename: str):
    """返回 Skill 图标内容（无鉴权，供前端卡片和编辑页展示）"""
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        raise HTTPException(status_code=404, detail="图标不存在")

    icon_path = os.path.join(settings.UPLOAD_DIR, "icons", safe_name)
    if not os.path.isfile(icon_path):
        raise HTTPException(status_code=404, detail="图标不存在")

    media_type, _ = mimetypes.guess_type(icon_path)
    return FileResponse(icon_path, media_type=media_type or "application/octet-stream")


@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.query(UploadedFileModel).filter(
        UploadedFileModel.id == file_id,
        UploadedFileModel.user_id == current_user.id,
    ).first()
    if not record:
        return ApiResponse.error(40201, "文件不存在")

    if not os.path.isfile(record.stored_path):
        return ApiResponse.error(40207, "文件已丢失")

    encoded_name = quote(record.original_name)
    return FileResponse(
        path=record.stored_path,
        filename=record.original_name,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        },
    )
