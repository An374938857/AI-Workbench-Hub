import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.models.model_provider import ModelProvider, ModelItem
from app.models.skill import SkillVersion
from app.models.user import User
from app.schemas.base import ApiResponse
from app.schemas.model_provider import (
    ModelProviderCreate,
    ModelProviderUpdate,
    ToggleRequest,
)
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
from app.services.llm.provider_factory import ProviderFactory
from app.utils.crypto import encrypt_api_key, decrypt_api_key, mask_api_key

router = APIRouter()


class UpdateModelTagsRequest(BaseModel):
    capability_tags: Optional[list[str]] = None
    speed_rating: Optional[str] = None
    cost_rating: Optional[str] = None
    description: Optional[str] = None
    max_output_tokens: Optional[int] = None


class EmbeddingConfigUpdateRequest(BaseModel):
    global_default_text_embedding_model_id: Optional[int] = None
    global_default_multimodal_embedding_model_id: Optional[int] = None
    rebuild_index: bool = False


def _is_embedding_model(model_name: str) -> bool:
    name = (model_name or "").lower()
    return "embedding" in name


def _provider_to_dict(p: ModelProvider) -> dict:
    try:
        raw_key = decrypt_api_key(p.api_key_encrypted)
        masked = mask_api_key(raw_key)
    except Exception:
        masked = "****"

    return {
        "id": p.id,
        "provider_name": p.provider_name,
        "provider_key": p.provider_key,
        "api_base_url": p.api_base_url,
        "api_key_masked": masked,
        "is_enabled": p.is_enabled,
        "protocol_type": p.protocol_type,
        "remark": p.remark,
        "last_test_result": p.last_test_result,
        "last_test_time": p.last_test_time.isoformat() if p.last_test_time else None,
        "models": [
            {
                "id": m.id,
                "model_name": m.model_name,
                "context_window": m.context_window,
                "is_enabled": m.is_enabled,
                "is_default": m.is_default,
                "capability_tags": m.capability_tags,
                "speed_rating": m.speed_rating,
                "cost_rating": m.cost_rating,
                "description": m.description,
                "max_output_tokens": m.max_output_tokens,
            }
            for m in (p.models or [])
        ],
    }


# ────── CRUD ──────

@router.get("")
def list_providers(
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    providers = db.query(ModelProvider).order_by(ModelProvider.id).all()
    return ApiResponse.success(data=[_provider_to_dict(p) for p in providers])


@router.post("")
def create_provider(
    body: ModelProviderCreate,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    if db.query(ModelProvider).filter(ModelProvider.provider_key == body.provider_key).first():
        return ApiResponse.error(40200, f"提供商标识 '{body.provider_key}' 已存在")

    provider = ModelProvider(
        provider_name=body.provider_name,
        provider_key=body.provider_key,
        api_base_url=body.api_base_url,
        api_key_encrypted=encrypt_api_key(body.api_key),
        protocol_type=body.protocol_type,
        remark=body.remark,
        last_test_result="untested",
    )
    db.add(provider)
    db.flush()

    for m in body.models:
        db.add(ModelItem(
            provider_id=provider.id,
            model_name=m.model_name,
            context_window=m.context_window,
            is_enabled=m.is_enabled,
        ))

    db.commit()
    db.refresh(provider)
    return ApiResponse.success(data=_provider_to_dict(provider), message="提供商创建成功")


@router.put("/{provider_id}")
def update_provider(
    provider_id: int,
    body: ModelProviderUpdate,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    provider = db.query(ModelProvider).filter(ModelProvider.id == provider_id).first()
    if not provider:
        return ApiResponse.error(40201, "提供商不存在")

    if body.provider_name is not None:
        provider.provider_name = body.provider_name
    if body.api_base_url is not None:
        provider.api_base_url = body.api_base_url
    if body.api_key and body.api_key.strip():
        provider.api_key_encrypted = encrypt_api_key(body.api_key)
    if body.protocol_type is not None:
        provider.protocol_type = body.protocol_type
    if body.remark is not None:
        provider.remark = body.remark

    if body.models is not None:
        existing_models = (
            db.query(ModelItem)
            .filter(ModelItem.provider_id == provider_id)
            .all()
        )
        existing_by_name = {m.model_name: m for m in existing_models}
        incoming_names: set[str] = set()

        for m in body.models:
            incoming_names.add(m.model_name)
            existing = existing_by_name.get(m.model_name)
            if existing:
                # 仅更新基础配置，保留标签/评分/默认标记等扩展字段
                existing.context_window = m.context_window
                existing.is_enabled = m.is_enabled
                continue

            db.add(ModelItem(
                provider_id=provider_id,
                model_name=m.model_name,
                context_window=m.context_window,
                is_enabled=m.is_enabled,
            ))

        for old in existing_models:
            if old.model_name not in incoming_names:
                db.delete(old)

    db.commit()
    ProviderFactory.clear_cache(provider_id)
    db.refresh(provider)
    return ApiResponse.success(data=_provider_to_dict(provider), message="提供商更新成功")


@router.delete("/{provider_id}")
def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    provider = db.query(ModelProvider).filter(ModelProvider.id == provider_id).first()
    if not provider:
        return ApiResponse.error(40201, "提供商不存在")

    skill_count = (
        db.query(SkillVersion)
        .filter(SkillVersion.model_provider_id == provider_id)
        .count()
    )
    if skill_count > 0:
        return ApiResponse.error(
            40202,
            f"该提供商下的模型正被 {skill_count} 个 Skill 版本使用，请先修改相关 Skill 的模型配置",
        )

    db.query(ModelItem).filter(ModelItem.provider_id == provider_id).delete()
    db.delete(provider)
    db.commit()
    ProviderFactory.clear_cache(provider_id)
    return ApiResponse.success(message="提供商删除成功")


# ────── 启用/停用 ──────

@router.post("/{provider_id}/toggle")
def toggle_provider(
    provider_id: int,
    body: ToggleRequest,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    provider = db.query(ModelProvider).filter(ModelProvider.id == provider_id).first()
    if not provider:
        return ApiResponse.error(40201, "提供商不存在")

    provider.is_enabled = body.is_enabled
    db.commit()
    action = "启用" if body.is_enabled else "停用"
    return ApiResponse.success(message=f"提供商已{action}")


# ────── 连通性测试 ──────

@router.post("/{provider_id}/test")
async def test_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    provider = db.query(ModelProvider).filter(ModelProvider.id == provider_id).first()
    if not provider:
        return ApiResponse.error(40201, "提供商不存在")

    enabled_models = [m for m in provider.models if m.is_enabled]
    first_model = next((m for m in enabled_models if not _is_embedding_model(m.model_name)), None)
    if not first_model:
        first_model = enabled_models[0] if enabled_models else None
    if not first_model:
        return ApiResponse.error(40203, "该提供商下没有已启用的模型")

    try:
        decrypt_api_key(provider.api_key_encrypted)
    except Exception:
        provider.last_test_result = "failed"
        provider.last_test_time = datetime.now()
        db.commit()
        return ApiResponse.error(50101, "API Key 解密失败，请重新配置", data={
            "result": "failed", "error_detail": "API Key 解密失败",
        })

    try:
        # Use protocol-aware provider for test_connection
        llm_provider = ProviderFactory.get_provider(provider_id, db)
        success, detail, elapsed_ms = await llm_provider.test_connection(first_model.model_name)

        if success:
            provider.last_test_result = "success"
            provider.last_test_time = datetime.now()
            db.commit()
            return ApiResponse.success(data={
                "result": "success",
                "response_time_ms": elapsed_ms,
                "test_model": first_model.model_name,
            })
        else:
            provider.last_test_result = "failed"
            provider.last_test_time = datetime.now()
            db.commit()
            return ApiResponse.error(50101, f"连通性测试失败：{detail}", data={
                "result": "failed",
                "error_detail": detail,
            })

    except Exception as e:
        provider.last_test_result = "failed"
        provider.last_test_time = datetime.now()
        db.commit()
        return ApiResponse.error(50101, f"连通性测试失败：{str(e)}", data={
            "result": "failed", "error_detail": str(e),
        })


# ────── 可用模型列表 ──────

@router.get("/available-models")
def available_models(
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("provider", "admin")),
):
    providers = (
        db.query(ModelProvider)
        .filter(ModelProvider.is_enabled == True)
        .order_by(ModelProvider.id)
        .all()
    )
    result = []
    for p in providers:
        for m in p.models:
            if m.is_enabled:
                result.append({
                    "provider_id": p.id,
                    "provider_name": p.provider_name,
                    "model_name": m.model_name,
                    "context_window": m.context_window,
                    "display_name": f"{p.provider_name} / {m.model_name}",
                })
    return ApiResponse.success(data=result)


# ────── 更新模型能力标签 ──────

@router.post("/{provider_id}/models/{model_name}/set-default")
def set_default_model(
    provider_id: int,
    model_name: str,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    target = (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(
            ModelItem.provider_id == provider_id,
            ModelItem.model_name == model_name,
            ModelItem.is_enabled == True,
            ModelProvider.is_enabled == True,
        )
        .first()
    )
    if not target:
        return ApiResponse.error(40205, "目标模型不可用或不存在")

    db.query(ModelItem).update({ModelItem.is_default: False}, synchronize_session=False)
    target.is_default = True
    db.commit()

    return ApiResponse.success(
        data={"provider_id": provider_id, "model_name": model_name},
        message="默认模型设置成功",
    )


@router.get("/default")
def get_default_model(
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("provider", "admin")),
):
    model = (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(
            ModelItem.is_default == True,
            ModelItem.is_enabled == True,
            ModelProvider.is_enabled == True,
        )
        .first()
    )
    if not model:
        return ApiResponse.success(data=None)

    provider = model.provider
    return ApiResponse.success(data={
        "provider_id": model.provider_id,
        "provider_name": provider.provider_name if provider else "",
        "model_name": model.model_name,
        "display_name": f"{provider.provider_name if provider else ''} / {model.model_name}",
    })


@router.get("/embedding-config")
def get_embedding_model_config(
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    return ApiResponse.success(data=get_embedding_config(db))


@router.put("/embedding-config")
@router.post("/embedding-config")
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


@router.get("/embedding-rebuild/tasks")
def list_embedding_rebuild_tasks(
    limit: int = 20,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    return ApiResponse.success(data=list_rebuild_tasks(db, limit=limit))


@router.get("/embedding-rebuild/tasks/{task_id}/items")
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


@router.post("/embedding-rebuild/tasks/{task_id}/start")
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


@router.post("/embedding-rebuild/tasks/{task_id}/retry-failed")
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


@router.post("/embedding-rebuild/tasks/{task_id}/cancel")
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


def _embedding_sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/embedding-rebuild/tasks/stream")
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


@router.put("/{provider_id}/models/{model_name}/tags")
def update_model_tags(
    provider_id: int,
    model_name: str,
    request: UpdateModelTagsRequest,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role("admin")),
):
    """更新模型的能力标签和元数据"""
    model = db.query(ModelItem).filter(
        ModelItem.provider_id == provider_id,
        ModelItem.model_name == model_name
    ).first()
    
    if not model:
        return ApiResponse.error(40401, "模型不存在")
    
    # 更新字段
    if request.capability_tags is not None:
        model.capability_tags = request.capability_tags
    if request.speed_rating is not None:
        model.speed_rating = request.speed_rating
    if request.cost_rating is not None:
        model.cost_rating = request.cost_rating
    if request.description is not None:
        model.description = request.description
    if request.max_output_tokens is not None:
        model.max_output_tokens = request.max_output_tokens
    
    db.commit()
    db.refresh(model)
    
    return ApiResponse.success(data={
        "model_name": model.model_name,
        "capability_tags": model.capability_tags,
        "speed_rating": model.speed_rating,
        "cost_rating": model.cost_rating,
        "description": model.description,
        "max_output_tokens": model.max_output_tokens
    })
