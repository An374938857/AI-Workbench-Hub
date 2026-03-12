import io
import logging
import os
import re
import shutil
import uuid
import zipfile
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db, require_role
from app.models.scene_tag import SceneTag
from app.models.skill import Skill, SkillVersion
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.base import ApiResponse
from app.schemas.skill import SkillCreate, SkillUpdate, PublishRequest

logger = logging.getLogger(__name__)


def _sync_skill_to_es(skill: Skill):
    """将已发布 Skill 同步到 ES 索引"""
    try:
        from app.services.skill_recommend import get_skill_recommend_service
        v = skill.published_version
        if not v:
            return
        svc = get_skill_recommend_service()
        svc.index_skill(
            skill_id=skill.id,
            name=skill.name,
            brief_desc=v.brief_desc,
            detail_desc=v.detail_desc,
            tags=[t.name for t in (skill.tags or [])],
            usage_example=v.usage_example or "",
            use_count=skill.use_count or 0,
            updated_at=skill.updated_at.isoformat() if skill.updated_at else None,
        )
    except Exception as e:
        logger.warning(f"同步 Skill {skill.id} 到 ES 失败: {e}")


def _delete_skill_from_es(skill_id: int):
    """从 ES 删除 Skill 索引"""
    try:
        from app.services.skill_recommend import get_skill_recommend_service
        get_skill_recommend_service().delete_skill(skill_id)
    except Exception as e:
        logger.warning(f"从 ES 删除 Skill {skill_id} 失败: {e}")

router = APIRouter()
settings = get_settings()


def _version_to_dict(v: Optional[SkillVersion]) -> Optional[dict]:
    if not v:
        return None
    return {
        "id": v.id,
        "version_number": v.version_number,
        "brief_desc": v.brief_desc,
        "detail_desc": v.detail_desc,
        "system_prompt": v.system_prompt,
        "welcome_message": v.welcome_message,
        "model_provider_id": v.model_provider_id,
        "model_name": v.model_name,
        "usage_example": v.usage_example,
        "package_path": v.package_path,
        "has_package": bool(v.package_path),
        "change_log": v.change_log,
        "mcp_load_mode": v.mcp_load_mode,
        "mcp_ids": [m.id for m in (v.bound_mcps or [])],
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _skill_summary(s: Skill) -> dict:
    pub_v = s.published_version
    draft_v = s.draft_version
    return {
        "id": s.id,
        "name": s.name,
        "icon_url": f"/api/files/icons/{os.path.basename(s.icon_path)}" if s.icon_path else None,
        "icon_emoji": s.icon_emoji,
        "status": s.status,
        "sort_weight": s.sort_weight,
        "use_count": s.use_count,
        "published_version": pub_v.version_number if pub_v else None,
        "draft_version": draft_v.version_number if draft_v else None,
        "tags": [{"id": t.id, "name": t.name} for t in (s.tags or [])],
        "model_name": pub_v.model_name if pub_v else None,
        "creator_name": s.creator.display_name if s.creator else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _skill_detail(s: Skill) -> dict:
    d = _skill_summary(s)
    d["published_version_detail"] = _version_to_dict(s.published_version)
    d["draft_version_detail"] = _version_to_dict(s.draft_version)
    return d


# ────── 列表 ──────

@router.get("")
def list_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    query = db.query(Skill)
    if current_user.role != "admin":
        query = query.filter(Skill.creator_id == current_user.id)
    if keyword:
        query = query.filter(Skill.name.like(f"%{keyword}%"))
    if status:
        query = query.filter(Skill.status == status)

    total = query.count()
    items = query.order_by(Skill.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ApiResponse.success(data={
        "items": [_skill_summary(s) for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# ────── 详情 ──────

@router.get("/{skill_id}")
def get_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权查看此 Skill")

    d = _skill_summary(skill)
    d["published_version_detail"] = _version_to_dict(skill.published_version)
    d["draft_version_detail"] = _version_to_dict(skill.draft_version)

    version_logs = (
        db.query(SkillVersion)
        .filter(SkillVersion.skill_id == skill_id, SkillVersion.change_log.isnot(None))
        .order_by(SkillVersion.version_number.desc())
        .all()
    )
    d["version_logs"] = [
        {"version": v.version_number, "change_log": v.change_log, "created_at": v.created_at.isoformat()}
        for v in version_logs
    ]
    return ApiResponse.success(data=d)


# ────── 解析技能包（临时上传）──────


def _parse_skill_md(content: str) -> dict:
    """从 SKILL.md Frontmatter 提取结构化信息（Claude Skill 规范）"""
    result = {
        "name": "",
        "brief_desc": "",
        "detail_desc": "",
        "system_prompt": content,
        "welcome_message": "",
    }

    match = re.match(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", content, flags=re.DOTALL)
    if not match:
        return result

    frontmatter = match.group(1)
    for line in frontmatter.splitlines():
        row = line.strip()
        if not row or row.startswith("#") or ":" not in row:
            continue

        key, value = row.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")

        if key == "name":
            result["name"] = value
        elif key == "description":
            result["brief_desc"] = value

    return result


def _parse_readme_md(content: str) -> str:
    """从 README.md 提取作为详细说明"""
    return content.strip()


@router.post("/parse-package")
async def parse_package(
    package: UploadFile = File(...),
    _u: User = Depends(require_role("provider", "admin")),
):
    filename = package.filename or ""
    if not filename.lower().endswith(".zip"):
        return ApiResponse.error(40100, "仅支持 .zip 格式的技能包")

    content = await package.read()
    if len(content) > 50 * 1024 * 1024:
        return ApiResponse.error(40101, "技能包不能超过 50MB")

    temp_id = uuid.uuid4().hex[:12]
    temp_dir = os.path.join(settings.UPLOAD_DIR, "temp_packages", temp_id)
    os.makedirs(temp_dir, exist_ok=True)

    zip_path = os.path.join(temp_dir, "package.zip")
    extract_dir = os.path.join(temp_dir, "files")

    try:
        with open(zip_path, "wb") as f:
            f.write(content)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        top_entries = [e for e in os.listdir(extract_dir) if not e.startswith(".")]
        if len(top_entries) == 1 and os.path.isdir(os.path.join(extract_dir, top_entries[0])):
            extract_dir = os.path.join(extract_dir, top_entries[0])

    except zipfile.BadZipFile:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ApiResponse.error(40102, "无效的 zip 文件")
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ApiResponse.error(50000, f"解压失败: {str(e)}")

    # 解析 SKILL.md / skill.md
    parsed = {"name": "", "brief_desc": "", "detail_desc": "", "system_prompt": "", "welcome_message": ""}
    skill_md_path = None
    for entry in os.listdir(extract_dir):
        if entry.lower() == "skill.md":
            skill_md_path = os.path.join(extract_dir, entry)
            break

    if not skill_md_path:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ApiResponse.error(40103, "技能包缺少 SKILL.md")

    with open(skill_md_path, "r", encoding="utf-8") as f:
        parsed = _parse_skill_md(f.read())

    if not parsed["name"] or not parsed["brief_desc"]:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ApiResponse.error(40104, "SKILL.md 必须包含 frontmatter 的 name 和 description 字段")

    # 解析 README.md 作为 detail_desc
    readme_path = os.path.join(extract_dir, "README.md")
    if os.path.isfile(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            parsed["detail_desc"] = _parse_readme_md(f.read())

    file_tree = _build_file_tree(extract_dir)

    # 将实际的 extract_dir 路径保存在元数据中，供后续 create 关联
    meta_path = os.path.join(temp_dir, "meta.txt")
    with open(meta_path, "w") as f:
        f.write(extract_dir)

    return ApiResponse.success(data={
        "temp_package_id": temp_id,
        "parsed_info": parsed,
        "file_tree": file_tree,
    })


# ────── 临时包文件预览 ──────

@router.get("/temp-package/{temp_id}/files/content")
def get_temp_file_content(
    temp_id: str,
    file_path: str = Query(..., min_length=1),
    _u: User = Depends(require_role("provider", "admin")),
):
    temp_dir = os.path.join(settings.UPLOAD_DIR, "temp_packages", temp_id)
    meta_path = os.path.join(temp_dir, "meta.txt")
    if not os.path.isfile(meta_path):
        return ApiResponse.error(40206, "临时包不存在或已过期")

    with open(meta_path, "r") as f:
        extract_dir = f.read().strip()

    abs_base = os.path.abspath(extract_dir)
    abs_target = os.path.abspath(os.path.join(extract_dir, file_path))
    if not abs_target.startswith(abs_base):
        return ApiResponse.error(40100, "非法的文件路径")
    if not os.path.isfile(abs_target):
        return ApiResponse.error(40207, "文件不存在")

    ext = os.path.splitext(abs_target)[1].lower()
    text_exts = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".js", ".ts", ".html", ".css", ".xml", ".csv", ".sh", ".bat", ".cfg", ".ini", ".env", ".mdc"}
    if ext not in text_exts:
        return ApiResponse.success(data={"file_path": file_path, "content": None, "is_text": False, "message": "不支持预览此文件格式"})

    try:
        with open(abs_target, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(abs_target, "r", encoding="gb18030") as f:
                content = f.read()
        except Exception:
            return ApiResponse.success(data={"file_path": file_path, "content": None, "is_text": False, "message": "文件编码不支持预览"})

    return ApiResponse.success(data={"file_path": file_path, "content": content, "is_text": True, "extension": ext})


# ────── 新建 ──────

@router.post("")
def create_skill(
    body: SkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = Skill(
        name=body.name,
        icon_emoji=body.icon_emoji,
        status="draft",
        creator_id=current_user.id,
    )
    db.add(skill)
    db.flush()

    if body.tag_ids:
        tags = db.query(SceneTag).filter(SceneTag.id.in_(body.tag_ids)).all()
        skill.tags = tags

    # 处理临时包 → 移动到正式目录
    package_path = None
    if body.temp_package_id:
        temp_dir = os.path.join(settings.UPLOAD_DIR, "temp_packages", body.temp_package_id)
        meta_path = os.path.join(temp_dir, "meta.txt")
        if os.path.isfile(meta_path):
            with open(meta_path, "r") as f:
                temp_extract_dir = f.read().strip()

            final_dir = os.path.join(settings.UPLOAD_DIR, "packages", str(skill.id), uuid.uuid4().hex[:8])
            os.makedirs(os.path.dirname(final_dir), exist_ok=True)
            shutil.copytree(temp_extract_dir, final_dir)
            package_path = final_dir
            shutil.rmtree(temp_dir, ignore_errors=True)

    version = SkillVersion(
        skill_id=skill.id,
        version_number=1,
        brief_desc=body.brief_desc,
        detail_desc=body.detail_desc,
        system_prompt=body.system_prompt,
        welcome_message=body.welcome_message,
        model_provider_id=body.model_provider_id,
        model_name=body.model_name,
        usage_example=body.usage_example,
        package_path=package_path,
        mcp_load_mode=body.mcp_load_mode,
    )
    db.add(version)
    db.flush()

    if body.mcp_load_mode == "selected" and body.mcp_ids:
        from app.models.mcp import Mcp
        mcps = db.query(Mcp).filter(Mcp.id.in_(body.mcp_ids)).all()
        version.bound_mcps = mcps

    skill.draft_version_id = version.id
    db.commit()
    db.refresh(skill)
    return ApiResponse.success(data=_skill_summary(skill), message="Skill 创建成功")


# ────── 编辑 ──────

@router.put("/{skill_id}")
def update_skill(
    skill_id: int,
    body: SkillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权编辑此 Skill")

    # 更新主表字段
    if body.name is not None:
        skill.name = body.name
    if body.icon_emoji is not None:
        skill.icon_emoji = body.icon_emoji
    if body.tag_ids is not None:
        tags = db.query(SceneTag).filter(SceneTag.id.in_(body.tag_ids)).all()
        skill.tags = tags

    # 确定要更新的版本：有草稿更新草稿，无草稿直接更新已发布版本
    is_draft = False
    if skill.draft_version_id:
        version = db.query(SkillVersion).filter(SkillVersion.id == skill.draft_version_id).first()
        is_draft = True
    elif skill.published_version_id:
        version = db.query(SkillVersion).filter(SkillVersion.id == skill.published_version_id).first()
    else:
        return ApiResponse.error(40203, "Skill 状态异常，无法编辑")

    # 更新版本字段
    if body.brief_desc is not None:
        version.brief_desc = body.brief_desc
    if body.detail_desc is not None:
        version.detail_desc = body.detail_desc
    if body.system_prompt is not None:
        version.system_prompt = body.system_prompt
    if body.welcome_message is not None:
        version.welcome_message = body.welcome_message
    if body.model_provider_id is not None:
        version.model_provider_id = body.model_provider_id
    if body.model_name is not None:
        version.model_name = body.model_name
    if body.usage_example is not None:
        version.usage_example = body.usage_example
    if body.mcp_load_mode is not None:
        version.mcp_load_mode = body.mcp_load_mode
    if body.mcp_ids is not None:
        from app.models.mcp import Mcp
        mcps = db.query(Mcp).filter(Mcp.id.in_(body.mcp_ids)).all()
        version.bound_mcps = mcps

    db.commit()
    db.refresh(skill)

    summary = _skill_summary(skill)
    summary["is_draft_save"] = is_draft
    if is_draft:
        return ApiResponse.success(data=summary, message="已保存为草稿，发布后生效")
    return ApiResponse.success(data=summary, message="保存成功")


# ────── 发布 ──────

@router.post("/{skill_id}/publish")
def publish_skill(
    skill_id: int,
    body: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权操作此 Skill")
    if not skill.draft_version_id:
        return ApiResponse.error(40204, "没有待发布的草稿版本")

    draft = db.query(SkillVersion).filter(SkillVersion.id == skill.draft_version_id).first()
    draft.change_log = body.change_log

    skill.published_version_id = skill.draft_version_id
    skill.draft_version_id = None
    skill.status = "published"

    db.commit()
    db.refresh(skill)
    _sync_skill_to_es(skill)
    return ApiResponse.success(data=_skill_summary(skill), message="Skill 发布成功")


# ────── 下架 / 上架 ──────

@router.post("/{skill_id}/offline")
def offline_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权操作此 Skill")

    skill.status = "offline"
    db.commit()
    _delete_skill_from_es(skill_id)
    return ApiResponse.success(message="Skill 已下架")


@router.post("/{skill_id}/online")
def online_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权操作此 Skill")
    if not skill.published_version_id:
        return ApiResponse.error(40205, "没有已发布的版本，无法上架")

    skill.status = "published"
    db.commit()
    _sync_skill_to_es(skill)
    return ApiResponse.success(message="Skill 已重新上架")


# ────── 删除 ──────

@router.delete("/{skill_id}")
def delete_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权操作此 Skill")

    # 清理关联：先清空 relationship 避免 SQLAlchemy 二次删除冲突
    skill.tags = []
    skill.published_version_id = None
    skill.draft_version_id = None
    db.flush()
    db.query(SkillVersion).filter(SkillVersion.skill_id == skill_id).delete()
    db.delete(skill)
    db.commit()
    _delete_skill_from_es(skill_id)
    return ApiResponse.success(message="Skill 删除成功")


# ────── 下载技能包 ──────

@router.get("/{skill_id}/download-package")
def download_package(
    skill_id: int,
    version_type: str = Query("draft", pattern="^(draft|published)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权操作此 Skill")

    vid = skill.draft_version_id if version_type == "draft" else skill.published_version_id
    if not vid:
        vid = skill.published_version_id if version_type == "draft" else skill.draft_version_id
    if not vid:
        return ApiResponse.error(40206, "没有可下载的版本")

    version = db.query(SkillVersion).filter(SkillVersion.id == vid).first()
    if not version or not version.package_path or not os.path.isdir(version.package_path):
        return ApiResponse.error(40206, "技能包文件不存在")

    buf = io.BytesIO()
    pkg_dir = version.package_path
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(pkg_dir):
            for f in files:
                abs_path = os.path.join(root, f)
                arc_name = os.path.relpath(abs_path, pkg_dir)
                zf.write(abs_path, arc_name)
    buf.seek(0)

    safe_name = skill.name.replace(" ", "_").replace("/", "_")
    filename = f"{safe_name}_v{version.version_number}.zip"
    encoded_filename = quote(filename)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


# ────── 图标上传 ──────

@router.post("/{skill_id}/upload-icon")
async def upload_icon(
    skill_id: int,
    icon: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")

    ext = os.path.splitext(icon.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".svg"):
        return ApiResponse.error(40100, "仅支持 png/jpg/svg 格式")
    if icon.size and icon.size > 2 * 1024 * 1024:
        return ApiResponse.error(40101, "图标文件不能超过 2MB")

    icon_dir = os.path.join(settings.UPLOAD_DIR, "icons")
    os.makedirs(icon_dir, exist_ok=True)
    filename = f"{skill_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(icon_dir, filename)

    content = await icon.read()
    with open(filepath, "wb") as f:
        f.write(content)

    skill.icon_path = filepath
    db.commit()
    return ApiResponse.success(
        data={"icon_url": f"/api/files/icons/{filename}"},
        message="图标上传成功",
    )


# ────── 查看反馈 ──────

@router.get("/{skill_id}/feedbacks")
def get_feedbacks(
    skill_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")

    query = db.query(Feedback).filter(Feedback.skill_id == skill_id)
    total = query.count()
    items = query.order_by(Feedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ApiResponse.success(data={
        "items": [
            {
                "id": f.id,
                "rating": f.rating,
                "comment": f.comment,
                "user_name": f.user.display_name if f.user else None,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# ────── 技能包管理 ──────

def _build_file_tree(dir_path: str, prefix: str = "") -> list:
    """递归构建目录树，返回 [{name, path, type, children?}]"""
    result = []
    try:
        entries = sorted(os.listdir(dir_path))
    except OSError:
        return result

    dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e)) and not e.startswith(".")]
    files = [e for e in entries if os.path.isfile(os.path.join(dir_path, e)) and not e.startswith(".")]

    for d in dirs:
        child_path = f"{prefix}/{d}" if prefix else d
        result.append({
            "name": d,
            "path": child_path,
            "type": "directory",
            "children": _build_file_tree(os.path.join(dir_path, d), child_path),
        })
    for f in files:
        file_path = f"{prefix}/{f}" if prefix else f
        ext = os.path.splitext(f)[1].lower()
        result.append({
            "name": f,
            "path": file_path,
            "type": "file",
            "extension": ext,
        })
    return result


@router.post("/{skill_id}/upload-package")
async def upload_package(
    skill_id: int,
    package: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权操作此 Skill")

    filename = package.filename or ""
    if not filename.lower().endswith(".zip"):
        return ApiResponse.error(40100, "仅支持 .zip 格式的技能包")

    content = await package.read()
    if len(content) > 50 * 1024 * 1024:
        return ApiResponse.error(40101, "技能包不能超过 50MB")

    # 确定存储目录
    pkg_dir = os.path.join(settings.UPLOAD_DIR, "packages", str(skill_id), uuid.uuid4().hex[:8])
    os.makedirs(pkg_dir, exist_ok=True)

    zip_path = os.path.join(pkg_dir, "package.zip")
    extract_dir = os.path.join(pkg_dir, "files")

    try:
        with open(zip_path, "wb") as f:
            f.write(content)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        # 如果解压后只有一个顶层目录，自动进入
        top_entries = [e for e in os.listdir(extract_dir) if not e.startswith(".")]
        if len(top_entries) == 1 and os.path.isdir(os.path.join(extract_dir, top_entries[0])):
            extract_dir = os.path.join(extract_dir, top_entries[0])

    except zipfile.BadZipFile:
        shutil.rmtree(pkg_dir, ignore_errors=True)
        return ApiResponse.error(40102, "无效的 zip 文件")
    except Exception as e:
        shutil.rmtree(pkg_dir, ignore_errors=True)
        return ApiResponse.error(50000, f"解压失败: {str(e)}")

    # 获取或创建草稿版本
    if skill.draft_version_id:
        version = db.query(SkillVersion).filter(SkillVersion.id == skill.draft_version_id).first()
    elif skill.published_version_id:
        pub = db.query(SkillVersion).filter(SkillVersion.id == skill.published_version_id).first()
        max_ver = (
            db.query(SkillVersion.version_number)
            .filter(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.version_number.desc())
            .first()
        )
        version = SkillVersion(
            skill_id=skill_id,
            version_number=(max_ver[0] if max_ver else 0) + 1,
            brief_desc=pub.brief_desc,
            detail_desc=pub.detail_desc,
            system_prompt=pub.system_prompt,
            welcome_message=pub.welcome_message,
            model_provider_id=pub.model_provider_id,
            model_name=pub.model_name,
            usage_example=pub.usage_example,
            package_path=pub.package_path,
        )
        db.add(version)
        db.flush()
        skill.draft_version_id = version.id
    else:
        return ApiResponse.error(40203, "Skill 状态异常")

    # 清理旧的 package 目录
    if version.package_path and os.path.exists(os.path.dirname(version.package_path)):
        old_pkg_root = version.package_path
        # 找到 packages/{skill_id}/{hash} 层级删除
        parent = os.path.dirname(old_pkg_root)
        if parent != os.path.join(settings.UPLOAD_DIR, "packages", str(skill_id)):
            parent = os.path.dirname(parent)
        if parent and "packages" in parent:
            shutil.rmtree(os.path.dirname(old_pkg_root), ignore_errors=True)

    version.package_path = extract_dir

    # 自动解析 SKILL.md 填充 system_prompt
    skill_md_path = os.path.join(extract_dir, "SKILL.md")
    if os.path.isfile(skill_md_path):
        try:
            with open(skill_md_path, "r", encoding="utf-8") as f:
                skill_md_content = f.read()
            version.system_prompt = skill_md_content
        except Exception:
            pass

    db.commit()
    db.refresh(skill)

    file_tree = _build_file_tree(extract_dir)
    return ApiResponse.success(data={
        "file_tree": file_tree,
        "skill": _skill_summary(skill),
    }, message="技能包上传成功")


@router.get("/{skill_id}/package-files")
def get_package_files(
    skill_id: int,
    version_type: str = Query("draft", pattern="^(draft|published)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权操作此 Skill")

    vid = skill.draft_version_id if version_type == "draft" else skill.published_version_id
    if not vid:
        return ApiResponse.success(data={"file_tree": [], "has_package": False})

    version = db.query(SkillVersion).filter(SkillVersion.id == vid).first()
    if not version or not version.package_path or not os.path.isdir(version.package_path):
        return ApiResponse.success(data={"file_tree": [], "has_package": False})

    file_tree = _build_file_tree(version.package_path)
    return ApiResponse.success(data={"file_tree": file_tree, "has_package": True})


@router.get("/{skill_id}/package-files/content")
def get_file_content(
    skill_id: int,
    file_path: str = Query(..., min_length=1),
    version_type: str = Query("draft", pattern="^(draft|published)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")
    if current_user.role != "admin" and skill.creator_id != current_user.id:
        return ApiResponse.error(40301, "无权操作此 Skill")

    vid = skill.draft_version_id if version_type == "draft" else skill.published_version_id
    if not vid:
        return ApiResponse.error(40206, "没有对应版本")

    version = db.query(SkillVersion).filter(SkillVersion.id == vid).first()
    if not version or not version.package_path:
        return ApiResponse.error(40206, "技能包不存在")

    # 安全检查：防止路径穿越
    abs_base = os.path.abspath(version.package_path)
    abs_target = os.path.abspath(os.path.join(version.package_path, file_path))
    if not abs_target.startswith(abs_base):
        return ApiResponse.error(40100, "非法的文件路径")

    if not os.path.isfile(abs_target):
        return ApiResponse.error(40207, "文件不存在")

    ext = os.path.splitext(abs_target)[1].lower()
    text_exts = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".js", ".ts", ".html", ".css", ".xml", ".csv", ".sh", ".bat", ".cfg", ".ini", ".env", ".mdc"}

    if ext not in text_exts:
        return ApiResponse.success(data={
            "file_path": file_path,
            "content": None,
            "is_text": False,
            "message": "不支持预览此文件格式",
        })

    try:
        with open(abs_target, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(abs_target, "r", encoding="gb18030") as f:
                content = f.read()
        except Exception:
            return ApiResponse.success(data={
                "file_path": file_path,
                "content": None,
                "is_text": False,
                "message": "文件编码不支持预览",
            })

    return ApiResponse.success(data={
        "file_path": file_path,
        "content": content,
        "is_text": True,
        "extension": ext,
    })
