import json
import os
import asyncio
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.deps import get_current_user, get_db, require_role
from app.models.asset import Asset
from app.models.mcp import Mcp
from app.models.user import User
from app.schemas.asset import AssetCreate, AssetUrlTitleResolveRequest
from app.schemas.base import ApiResponse
from app.services.embedding_governance import mark_task_queued, schedule_rebuild_for_asset
from app.services.embedding_rebuild_runtime import get_embedding_rebuild_runtime
from app.services.file_preview_service import build_preview_payload
from app.services.mcp.tool_executor import ToolExecutor
from app.services.mcp_service import get_client_manager, get_decrypted_config

router = APIRouter()
ALLOWED_UPLOAD_TYPES = {
    "bmp",
    "csv",
    "docx",
    "gif",
    "html",
    "jpeg",
    "jpg",
    "json",
    "md",
    "pdf",
    "png",
    "svg",
    "txt",
    "webp",
    "xlsx",
}
TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_PATTERN = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
LINK_PATTERN = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
ATTR_PATTERN = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:\-]*)\s*=\s*([\'"])(.*?)\2', re.IGNORECASE | re.DOTALL)
YUQUE_HOST_SUFFIXES = ("yuque.com", "yuque.cn")


class AssetRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)


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
        "content": asset.content,
        "source_url": asset.source_url,
        "file_ref": asset.file_ref,
        "file_type": file_type,
        "file_size": file_size,
        "snapshot_markdown": asset.snapshot_markdown,
        "refetch_status": asset.refetch_status,
        "last_refetched_at": asset.last_refetched_at.isoformat() if asset.last_refetched_at else None,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _get_asset_or_error(asset_id: int, db: Session) -> tuple[Asset | None, ApiResponse | None]:
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return None, ApiResponse.error(40401, "资料不存在")
    return asset, None


def _resolve_asset_file_path(file_ref: str) -> Path:
    return (Path.cwd() / file_ref).resolve()


def _detect_file_type(asset: Asset) -> str:
    if asset.file_ref:
        ext = Path(asset.file_ref).suffix.lower().lstrip(".")
        if ext:
            return ext
    if asset.title:
        ext = Path(asset.title).suffix.lower().lstrip(".")
        if ext:
            return ext
    return "file"


def _build_asset_filename(asset: Asset) -> str:
    if asset.title:
        return asset.title
    if asset.file_ref:
        return Path(asset.file_ref).name
    return f"asset-{asset.id}"


def _build_markdown_filename(filename: str) -> str:
    if filename.lower().endswith(".md"):
        return filename
    return f"{filename}.md"


def _extract_html_title(html: str) -> str | None:
    if not html:
        return None
    matched = TITLE_PATTERN.search(html)
    if not matched:
        return None
    title = unescape(matched.group(1)).strip()
    return re.sub(r"\s+", " ", title)[:200] if title else None


def _extract_tag_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _quote, value in ATTR_PATTERN.findall(tag):
        attrs[key.lower()] = unescape(value).strip()
    return attrs


def _extract_meta_content(html: str, keys: list[str], attr_name: str = "name") -> str | None:
    targets = {item.lower() for item in keys}
    for tag in META_PATTERN.findall(html):
        attrs = _extract_tag_attrs(tag)
        attr_value = attrs.get(attr_name, "").lower()
        if attr_value in targets:
            content = attrs.get("content", "").strip()
            if content:
                return re.sub(r"\s+", " ", content)[:500]
    return None


def _extract_icon_url(html: str, base_url: str) -> str:
    for tag in LINK_PATTERN.findall(html):
        attrs = _extract_tag_attrs(tag)
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href", "").strip()
        if "icon" in rel and href:
            return urljoin(base_url, href)
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico" if parsed.scheme and parsed.netloc else ""


def _normalize_url(source_url: str) -> str:
    source_url = source_url.strip()
    if source_url and not (source_url.startswith("http://") or source_url.startswith("https://")):
        source_url = f"https://{source_url}"

    # 兼容语雀登录跳转链接，自动提取 goto 中的真实文档地址
    try:
        parsed = urlparse(source_url)
        host = parsed.netloc.lower()
        if (
            host
            and (host == "yuque.com" or host.endswith(".yuque.com") or host == "yuque.cn" or host.endswith(".yuque.cn"))
            and parsed.path == "/login"
        ):
            goto_values = parse_qs(parsed.query).get("goto", [])
            if goto_values:
                goto_url = unquote(goto_values[0]).strip()
                if goto_url:
                    if not (goto_url.startswith("http://") or goto_url.startswith("https://")):
                        goto_url = f"https://{goto_url.lstrip('/')}"
                    return goto_url
    except Exception:
        pass

    return source_url


def _is_yuque_url(source_url: str) -> bool:
    try:
        parsed = urlparse(source_url)
    except Exception:
        return False
    host = parsed.netloc.lower()
    if not host:
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in YUQUE_HOST_SUFFIXES)


def _has_enabled_dragon_mcp(db: Session) -> bool:
    return (
        db.query(Mcp.id)
        .filter(
            Mcp.name == "dragon-mcp",
            Mcp.is_enabled.is_(True),
        )
        .first()
        is not None
    )


def _normalize_markdown_title(preferred_title: str | None) -> str:
    raw_title = (preferred_title or "").strip()
    raw_stem = Path(raw_title).stem if raw_title else "yuque_doc"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_stem).strip("._-") or "yuque_doc"
    if raw_title:
        return raw_title if raw_title.lower().endswith(".md") else f"{raw_title}.md"
    return f"{safe_stem}.md"


def _resolve_yuque_title_candidate(
    returned_name: str | None,
    preferred_title: str | None,
    mcp_filename: str | None,
) -> str | None:
    for candidate in (returned_name, preferred_title, mcp_filename):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _persist_markdown_to_asset_file(
    scope_type: str,
    scope_id: int,
    preferred_title: str | None,
    markdown_content: str,
) -> tuple[str, str]:
    settings = get_settings()
    upload_root = Path(settings.UPLOAD_DIR).resolve() / "assets" / scope_type.lower() / str(scope_id)
    upload_root.mkdir(parents=True, exist_ok=True)

    raw_title = (preferred_title or "").strip()
    raw_stem = Path(raw_title).stem if raw_title else "yuque_doc"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_stem).strip("._-") or "yuque_doc"
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}_{safe_stem[:48]}.md"
    target_path = upload_root / filename
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    file_ref = os.path.relpath(target_path, Path.cwd())
    normalized_title = _normalize_markdown_title(preferred_title)
    return file_ref, normalized_title


def _overwrite_asset_file(file_ref: str, markdown_content: str) -> bool:
    try:
        file_path = _resolve_asset_file_path(file_ref)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        return True
    except Exception:
        return False


async def _auto_schedule_index_for_asset(
    db: Session,
    asset: Asset,
    trigger_user_id: int | None,
) -> None:
    try:
        created_tasks = schedule_rebuild_for_asset(db, asset, trigger_user_id)
        if not created_tasks:
            return

        task_ids: list[int] = []
        for task in created_tasks:
            task_id = int(task.get("task_id") or 0)
            if task_id <= 0:
                continue
            mark_task_queued(db, task_id)
            task_ids.append(task_id)
        db.commit()

        runtime = get_embedding_rebuild_runtime()
        for task_id in task_ids:
            await runtime.start_task(task_id)
    except Exception:
        db.rollback()
        raise


@router.get("")
def list_assets(
    scope_type: str | None = Query(None),
    scope_id: int | None = Query(None),
    node_code: str | None = Query(None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = db.query(Asset)
    if scope_type:
        query = query.filter(Asset.scope_type == scope_type)
    if scope_id:
        query = query.filter(Asset.scope_id == scope_id)
    if node_code:
        query = query.filter(Asset.node_code == node_code)
    assets = query.order_by(Asset.id.desc()).all()
    return ApiResponse.success(data=[_asset_to_dict(item) for item in assets])


@router.post("")
async def create_asset(
    body: AssetCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    source_url = _normalize_url(body.source_url or "")

    if body.asset_type in {"URL", "YUQUE_URL"} and not source_url:
        return ApiResponse.error(40001, "URL 类型资料必须提供 source_url")
    if body.asset_type == "MARKDOWN" and not body.content:
        return ApiResponse.error(40001, "MARKDOWN 类型资料必须提供 content")
    if body.asset_type == "FILE" and not body.file_ref:
        return ApiResponse.error(40001, "FILE 类型资料必须提供 file_ref")

    is_yuque_source = body.asset_type == "YUQUE_URL" or (
        body.asset_type == "URL" and source_url and _is_yuque_url(source_url)
    )
    dragon_enabled = _has_enabled_dragon_mcp(db) if is_yuque_source else False
    if is_yuque_source and dragon_enabled:
        normalized_title = body.title or "语雀文档"
        asset = Asset(
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            node_code=body.node_code,
            asset_type="YUQUE_URL",
            title=normalized_title,
            source_url=source_url,
            refetch_status="PENDING",
            created_by=current_user.id,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        background_tasks.add_task(_ingest_yuque_asset_async, asset.id, source_url, body.title)
        return ApiResponse.success(data=_asset_to_dict(asset), message="语雀文档已提交后台下载")

    asset = Asset(
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        node_code=body.node_code,
        asset_type="URL" if is_yuque_source else body.asset_type,
        title=body.title,
        content=body.content,
        source_url=source_url or None,
        file_ref=body.file_ref,
        created_by=current_user.id,
    )

    db.add(asset)
    db.commit()
    db.refresh(asset)
    if asset.asset_type == "FILE":
        await _auto_schedule_index_for_asset(db, asset, current_user.id)
    return ApiResponse.success(data=_asset_to_dict(asset))


@router.post("/resolve-url-title")
def resolve_url_title(
    body: AssetUrlTitleResolveRequest,
    _current_user: User = Depends(get_current_user),
):
    source_url = _normalize_url(body.source_url or "")
    if not source_url:
        return ApiResponse.error(40001, "URL 不能为空")

    try:
        response = httpx.get(
            source_url,
            follow_redirects=True,
            timeout=8.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AssetTitleResolver/1.0)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return ApiResponse.error(40001, f"URL 访问失败：{str(exc)}")

    html = response.text
    resolved_url = _normalize_url(str(response.url))
    if _is_yuque_url(source_url):
        resolved_parsed = urlparse(resolved_url)
        # 语雀未登录时会重定向到 /login?goto=...，此处保持/恢复为文档直链，避免前端回填成登录链接
        if resolved_parsed.path == "/login" or not _is_yuque_url(resolved_url):
            resolved_url = source_url
    title = (
        _extract_meta_content(html, ["og:title"], attr_name="property")
        or _extract_meta_content(html, ["twitter:title"], attr_name="name")
        or _extract_html_title(html)
    )
    if not title:
        return ApiResponse.error(40001, "未解析到网页标题")
    description = (
        _extract_meta_content(html, ["description"], attr_name="name")
        or _extract_meta_content(html, ["og:description"], attr_name="property")
        or _extract_meta_content(html, ["twitter:description"], attr_name="name")
    )
    image_url = (
        _extract_meta_content(html, ["og:image"], attr_name="property")
        or _extract_meta_content(html, ["twitter:image"], attr_name="name")
    )
    card_image_url = urljoin(resolved_url, image_url) if image_url else None
    icon_url = _extract_icon_url(html, resolved_url)

    return ApiResponse.success(
        data={
            "title": title,
            "description": description or "",
            "source_url": resolved_url,
            "icon_url": icon_url,
            "image_url": card_image_url,
        }
    )


def _fetch_yuque_snapshot(db: Session, source_url: str) -> tuple[bool, str, dict]:
    mcp = (
        db.query(Mcp)
        .filter(
            Mcp.name == "dragon-mcp",
            Mcp.is_enabled.is_(True),
        )
        .first()
    )
    if not mcp:
        return False, "未找到可用的 dragon-mcp 配置", {}

    tool_executor = ToolExecutor(get_client_manager())
    result = asyncio.run(
        tool_executor.execute(
            mcp_id=mcp.id,
            config_json=get_decrypted_config(mcp),
            transport_type=mcp.transport_type,
            tool_name="get_yuque_doc",
            arguments={"yuqueUrl": source_url},
            timeout_seconds=mcp.timeout_seconds,
            max_retries=mcp.max_retries,
            circuit_breaker_threshold=mcp.circuit_breaker_threshold,
            circuit_breaker_recovery=mcp.circuit_breaker_recovery,
        )
    )
    if not result.success:
        return False, result.error or "MCP 调用失败", {}

    content = result.content.strip()
    if not content:
        return False, "MCP 返回内容为空", {}

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return True, content, {}

    if isinstance(payload, dict):
        data = payload.get("data")
        returned_name = None
        mcp_filename = None
        for container in (data, payload):
            if not isinstance(container, dict):
                continue
            for key in ("name", "title", "fileName", "filename"):
                value = container.get(key)
                if isinstance(value, str) and value.strip():
                    returned_name = value.strip()
                    break
            if returned_name:
                break

        if isinstance(data, dict):
            file_path = data.get("filePath") or data.get("file_path")
            if isinstance(file_path, str) and file_path.strip():
                mcp_filename = Path(file_path.strip()).name or None
                local_file = Path(file_path.strip())
                if local_file.exists() and local_file.is_file():
                    try:
                        return True, local_file.read_text(encoding="utf-8"), {
                            "returned_name": returned_name,
                            "mcp_filename": mcp_filename,
                        }
                    except Exception:
                        # 回退使用宽松解码，避免因少量异常字符导致整次抓取失败
                        return True, local_file.read_text(encoding="utf-8", errors="ignore"), {
                            "returned_name": returned_name,
                            "mcp_filename": mcp_filename,
                        }
        for key in ("snapshot_markdown", "markdown", "content", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return True, value, {
                    "returned_name": returned_name,
                    "mcp_filename": mcp_filename,
                }
        if isinstance(data, dict):
            for key in ("markdown", "content", "text"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return True, value, {
                        "returned_name": returned_name,
                        "mcp_filename": mcp_filename,
                    }
    return True, content, {}


def _ingest_yuque_asset_async(asset_id: int, source_url: str, preferred_title: str | None) -> None:
    db = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return

        asset.refetch_status = "RUNNING"
        db.commit()

        success, snapshot_or_error, meta = _fetch_yuque_snapshot(db=db, source_url=source_url)
        if success:
            final_title = _resolve_yuque_title_candidate(
                meta.get("returned_name"),
                preferred_title or asset.title,
                meta.get("mcp_filename"),
            )
            file_ref, normalized_title = _persist_markdown_to_asset_file(
                scope_type=asset.scope_type,
                scope_id=asset.scope_id,
                preferred_title=final_title,
                markdown_content=snapshot_or_error,
            )
            asset.asset_type = "FILE"
            asset.file_ref = file_ref
            asset.title = normalized_title
            asset.snapshot_markdown = snapshot_or_error
            asset.refetch_status = "SUCCESS"
            asset.last_refetched_at = datetime.now()
            asset.source_url = source_url
            db.commit()
            return

        asset.refetch_status = "FAILED"
        asset.snapshot_markdown = f"# 语雀拉取失败\n\n{snapshot_or_error}"
        asset.last_refetched_at = datetime.now()
        asset.source_url = source_url
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if failed_asset:
            failed_asset.refetch_status = "FAILED"
            failed_asset.snapshot_markdown = f"# 语雀拉取失败\n\n后台任务异常：{str(exc)}"
            failed_asset.last_refetched_at = datetime.now()
            db.commit()
    finally:
        db.close()


def _refetch_yuque_asset_async(asset_id: int, source_url: str) -> None:
    db = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return

        success, snapshot_or_error, meta = _fetch_yuque_snapshot(db=db, source_url=source_url)
        if success:
            final_title = _resolve_yuque_title_candidate(
                meta.get("returned_name"),
                asset.title,
                meta.get("mcp_filename"),
            )
            if asset.asset_type == "FILE" and asset.file_ref:
                write_ok = _overwrite_asset_file(asset.file_ref, snapshot_or_error)
                if not write_ok:
                    asset.refetch_status = "FAILED"
                    asset.snapshot_markdown = "# 语雀拉取失败\n\n覆盖本地资料文件失败"
                else:
                    asset.refetch_status = "SUCCESS"
                    asset.snapshot_markdown = snapshot_or_error
                    if final_title:
                        asset.title = _normalize_markdown_title(final_title)
            else:
                file_ref, normalized_title = _persist_markdown_to_asset_file(
                    scope_type=asset.scope_type,
                    scope_id=asset.scope_id,
                    preferred_title=final_title,
                    markdown_content=snapshot_or_error,
                )
                asset.asset_type = "FILE"
                asset.file_ref = file_ref
                asset.title = normalized_title
                asset.refetch_status = "SUCCESS"
                asset.snapshot_markdown = snapshot_or_error
            asset.source_url = source_url
        else:
            asset.refetch_status = "FAILED"
            asset.snapshot_markdown = f"# 语雀拉取失败\n\n{snapshot_or_error}"

        asset.last_refetched_at = datetime.now()
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if failed_asset:
            failed_asset.refetch_status = "FAILED"
            failed_asset.snapshot_markdown = f"# 语雀拉取失败\n\n后台任务异常：{str(exc)}"
            failed_asset.last_refetched_at = datetime.now()
            db.commit()
    finally:
        db.close()


@router.post("/upload-file")
async def upload_asset_file(
    scope_type: str = Form(...),
    scope_id: int = Form(...),
    node_code: str | None = Form(None),
    title: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    if scope_type not in {"PROJECT", "REQUIREMENT"}:
        return ApiResponse.error(40001, "scope_type 仅支持 PROJECT/REQUIREMENT")
    if scope_id <= 0:
        return ApiResponse.error(40001, "scope_id 必须为正整数")

    settings = get_settings()
    upload_root = Path(settings.UPLOAD_DIR).resolve() / "assets" / scope_type.lower() / str(scope_id)
    upload_root.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "unnamed"
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in ALLOWED_UPLOAD_TYPES:
        return ApiResponse.error(40001, f"不支持的文件格式，仅支持 {', '.join(sorted(ALLOWED_UPLOAD_TYPES))}")
    suffix = Path(original_name).suffix
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}{suffix}"
    target_path = upload_root / safe_name

    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)

    file_ref = os.path.relpath(target_path, Path.cwd())
    asset = Asset(
        scope_type=scope_type,
        scope_id=scope_id,
        node_code=node_code,
        asset_type="FILE",
        title=title or original_name,
        file_ref=file_ref,
        created_by=current_user.id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    await _auto_schedule_index_for_asset(db, asset, current_user.id)
    return ApiResponse.success(data=_asset_to_dict(asset), message="资料文件上传成功")


@router.post("/project-file-upload")
async def upload_project_asset_file(
    project_id: int = Form(...),
    node_code: str | None = Form(None),
    title: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    return await upload_asset_file(
        scope_type="PROJECT",
        scope_id=project_id,
        node_code=node_code,
        title=title,
        file=file,
        db=db,
        current_user=current_user,
    )


@router.get("/{asset_id}/preview")
def preview_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    asset, error = _get_asset_or_error(asset_id, db)
    if error:
        return error

    if asset.asset_type == "MARKDOWN":
        content = asset.content or asset.snapshot_markdown or ""
        return ApiResponse.success(
            data={
                "asset_id": asset.id,
                "filename": _build_asset_filename(asset),
                "file_type": "md",
                "file_size": len(content.encode("utf-8")),
                "preview_type": "markdown",
                "content": content[:100000],
                "truncated": len(content) > 100000,
            }
        )

    if asset.asset_type in {"URL", "YUQUE_URL"}:
        if not asset.source_url:
            return ApiResponse.success(
                data={
                    "asset_id": asset.id,
                    "filename": _build_asset_filename(asset),
                    "file_type": "url",
                    "file_size": 0,
                    "preview_type": "download_only",
                    "preview_notice": "该资料未配置 URL，无法预览。",
                }
            )
        is_yuque = _is_yuque_url(asset.source_url)
        return ApiResponse.success(
            data={
                "asset_id": asset.id,
                "filename": _build_asset_filename(asset),
                "file_type": "url",
                "file_size": 0,
                "preview_type": "download_only",
                "preview_notice": "该资料为语雀链接，支持打开原文并下载历史抓取的 Markdown 快照。"
                if is_yuque
                else "该资料为链接类型，请在新窗口打开。",
                "preview_url": asset.source_url,
                "download_url": f"/api/v1/assets/{asset.id}/download" if is_yuque else asset.source_url,
            }
        )

    if asset.asset_type != "FILE" or not asset.file_ref:
        return ApiResponse.error(40001, "该资料类型不支持预览")

    file_path = _resolve_asset_file_path(asset.file_ref)
    if not file_path.exists() or not file_path.is_file():
        return ApiResponse.error(40401, "资料文件不存在")

    file_type = _detect_file_type(asset)
    filename = _build_asset_filename(asset)
    file_size = file_path.stat().st_size
    download_url = f"/api/v1/assets/{asset.id}/download"
    payload = build_preview_payload(
        file_path=file_path,
        file_type=file_type,
        filename=filename,
        file_size=file_size,
        download_url=download_url,
    )
    payload["asset_id"] = asset.id
    return ApiResponse.success(data=payload)


@router.get("/{asset_id}/download")
def download_asset_file(
    asset_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    asset, error = _get_asset_or_error(asset_id, db)
    if error:
        return error
    if asset.asset_type == "FILE" and asset.file_ref:
        file_path = _resolve_asset_file_path(asset.file_ref)
        if not file_path.exists() or not file_path.is_file():
            return ApiResponse.error(40401, "资料文件不存在")

        return FileResponse(
            str(file_path),
            filename=_build_asset_filename(asset),
            media_type="application/octet-stream",
        )

    if asset.asset_type in {"URL", "YUQUE_URL"} and asset.source_url and _is_yuque_url(asset.source_url):
        # 优先下载当时通过 MCP 抓取并落盘的 Markdown 文件
        if asset.file_ref:
            file_path = _resolve_asset_file_path(asset.file_ref)
            if file_path.exists() and file_path.is_file():
                return FileResponse(
                    str(file_path),
                    filename=_build_markdown_filename(_build_asset_filename(asset)),
                    media_type="text/markdown; charset=utf-8",
                )

        snapshot_markdown = (asset.snapshot_markdown or "").strip()
        if snapshot_markdown:
            filename = _build_markdown_filename(_build_asset_filename(asset))
            encoded = quote(filename)
            return Response(
                content=snapshot_markdown,
                media_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"
                },
            )
        return ApiResponse.error(40401, "语雀资料缺少可下载的 Markdown 快照")

    return ApiResponse.error(40001, "仅 FILE 类型或语雀 URL 资料支持下载")


@router.delete("/{asset_id}")
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("user", "admin")),
):
    asset, error = _get_asset_or_error(asset_id, db)
    if error:
        return error

    if asset.asset_type == "FILE" and asset.file_ref:
        file_path = _resolve_asset_file_path(asset.file_ref)
        if file_path.exists() and file_path.is_file():
            try:
                file_path.unlink()
            except Exception:
                # 文件删除失败不阻塞记录删除，避免脏数据长期残留
                pass

    db.delete(asset)
    db.commit()
    return ApiResponse.success(data={"id": asset_id}, message="资料已删除")


@router.put("/{asset_id}/rename")
def rename_asset(
    asset_id: int,
    body: AssetRenameRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("user", "admin")),
):
    asset, error = _get_asset_or_error(asset_id, db)
    if error:
        return error

    new_title = body.title.strip()
    if not new_title:
        return ApiResponse.error(40001, "新文件名不能为空")
    if "/" in new_title or "\\" in new_title:
        return ApiResponse.error(40001, "文件名不能包含路径分隔符")
    if new_title in {".", ".."}:
        return ApiResponse.error(40001, "文件名不合法")
    if new_title == (asset.title or ""):
        return ApiResponse.success(data=_asset_to_dict(asset), message="文件名未变更")

    asset.title = new_title
    db.commit()
    db.refresh(asset)
    return ApiResponse.success(data=_asset_to_dict(asset), message="资料重命名成功")


@router.post("/{asset_id}/refetch")
def refetch_asset(
    asset_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("user", "admin")),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return ApiResponse.error(40401, "资料不存在")

    source_url = _normalize_url(asset.source_url or "")
    if not source_url:
        return ApiResponse.error(40001, "该资料没有可重抓的 source_url")

    dragon_enabled = _has_enabled_dragon_mcp(db)
    if _is_yuque_url(source_url) and dragon_enabled:
        asset.refetch_status = "RUNNING"
        asset.source_url = source_url
        asset.last_refetched_at = datetime.now()
        db.commit()
        db.refresh(asset)
        background_tasks.add_task(_refetch_yuque_asset_async, asset.id, source_url)
        return ApiResponse.success(
            data=_asset_to_dict(asset),
            message="语雀资料重抓任务已提交，后台执行中",
        )
    elif asset.asset_type in {"URL", "YUQUE_URL"}:
        asset.refetch_status = "SUCCESS"
        asset.snapshot_markdown = (
            f"# Snapshot\n\nRefetched from {source_url}\n\nOperator: {current_user.username}"
        )
        asset.source_url = source_url
    else:
        return ApiResponse.error(40001, "仅 URL 或语雀来源资料支持重抓")

    asset.last_refetched_at = datetime.now()
    db.commit()
    db.refresh(asset)
    return ApiResponse.success(
        data=_asset_to_dict(asset),
        message="重抓成功" if asset.refetch_status == "SUCCESS" else "重抓失败",
    )
