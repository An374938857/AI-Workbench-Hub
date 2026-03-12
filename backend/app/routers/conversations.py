import asyncio
import copy
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.deps import get_db, get_current_user
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.mcp import Mcp
from app.models.model_provider import ModelItem, ModelProvider
from app.models.skill import Skill, SkillVersion
from app.models.uploaded_file import UploadedFile
from app.models.usage_log import UsageLog
from app.models.user import User
from app.models.system_prompt_template import SystemPromptTemplate
from app.models.workflow import WorkflowInstanceNodeOutput, WorkflowNodeConversation
from app.routers import conversation_prompt_templates, conversation_sandbox, conversation_skills
from app.routers.conversations_shared import (
    build_skill_display_name,
    serialize_conversation_skill_info,
)
from app.schemas.base import ApiResponse
from app.schemas.conversation import SendMessageRequest
from app.services.llm.provider_factory import ProviderFactory
from app.services.mcp_service import get_client_manager
from app.services.mcp.tool_executor import ToolExecutor
from app.services.fallback_service import FallbackService
from app.services.conversation_live_state import (
    build_live_state_detail_version,
    serialize_live_execution,
    serialize_live_state_snapshot,
)
from app.services.conversation_events import get_conversation_event_bus
from app.services.conversation_sidebar_signal import (
    SIDEBAR_SIGNAL_UNREAD_REPLY,
    mark_sidebar_signal_read,
    serialize_sidebar_signal,
)
from app.services.search_service import search_service
from app.services.conversation_execution import ConversationExecutionEngine
from app.services.conversation_runtime import get_conversation_runtime_registry
from app.services.prompt_combiner import PromptCombiner
from app.services.skill_activation_manager import SkillActivationManager
from app.services.sandbox_file_manager import SandboxFileManager
from app.services.sandbox_change_counter import increase_sandbox_unread_change_count
from app.services.reference_service import (
    assemble_reference_context,
    write_reference_audit,
)
from app.utils.token_counter import (
    count_tokens,
    estimate_total_context,
)

router = APIRouter()

_serialize_live_execution = serialize_live_execution
_build_live_state_detail_version = build_live_state_detail_version
_serialize_live_state_snapshot = serialize_live_state_snapshot
_serialize_sidebar_signal = serialize_sidebar_signal


class CreateConversationRequest(BaseModel):
    skill_id: Optional[int] = None
    prompt_template_id: Optional[int] = None  # 新增：Prompt 模板 ID
    is_test: bool = False


# ────── 创建对话 ──────


@router.post("")
def create_conversation(
    body: CreateConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 获取全局默认 Prompt 模板
    if not body.prompt_template_id:
        # 尝试获取全局默认模板
        default_template = (
            db.query(SystemPromptTemplate)
            .filter(SystemPromptTemplate.is_global_default == True)
            .first()
        )
        if default_template:
            body.prompt_template_id = default_template.id

    # 自由对话（不绑定 Skill）
    if not body.skill_id:
        conv = Conversation(
            user_id=current_user.id,
            skill_id=None,
            skill_version_id=None,
            prompt_template_id=body.prompt_template_id,
            is_test=False,
        )
        db.add(conv)
        db.flush()

        # 使用 PromptCombiner 组合默认 prompt 和模板
        combined_prompt = PromptCombiner.combine_prompts(db, conv, current_user.id)
        combined_prompt = PromptCombiner.truncate_if_needed(combined_prompt)

        if combined_prompt:
            # 插入 system 消息
            sys_msg = Message(
                conversation_id=conv.id,
                role="system",
                content=combined_prompt,
                token_count=count_tokens(combined_prompt),
                parent_id=None,
                branch_index=0,
                is_active=True,
            )
            db.add(sys_msg)
            db.flush()

            # 插入欢迎消息
            welcome_content = (
                "你好！我是业财产品 AI 助手，很高兴为你服务。请问有什么可以帮你？"
            )
            welcome_msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content=welcome_content,
                token_count=count_tokens(welcome_content),
                parent_id=sys_msg.id,
                branch_index=0,
                is_active=True,
            )
            db.add(welcome_msg)
            db.commit()
            db.refresh(conv)
            db.refresh(welcome_msg)
            get_conversation_event_bus().publish_conversation_snapshot_nowait(
                conv=conv,
                event_type="conversation.created",
            )

            return ApiResponse.success(
                data={
                    "conversation_id": conv.id,
                    "skill_name": "自由对话",
                    "active_skills": [],
                    "prompt_template_id": conv.prompt_template_id,
                    "messages": [
                        {
                            "id": welcome_msg.id,
                            "role": "assistant",
                            "content": welcome_msg.content,
                            "created_at": welcome_msg.created_at.isoformat(),
                        }
                    ],
                }
            )
        else:
            db.commit()
            db.refresh(conv)
            get_conversation_event_bus().publish_conversation_snapshot_nowait(
                conv=conv,
                event_type="conversation.created",
            )
            return ApiResponse.success(
                data={
                    "conversation_id": conv.id,
                    "skill_name": "自由对话",
                    "active_skills": [],
                    "prompt_template_id": conv.prompt_template_id,
                    "messages": [],
                }
            )

    # 绑定 Skill 的对话
    skill = db.query(Skill).filter(Skill.id == body.skill_id).first()
    if not skill:
        return ApiResponse.error(40201, "Skill 不存在")

    if body.is_test:
        version_id = skill.draft_version_id or skill.published_version_id
    else:
        if skill.status != "published":
            return ApiResponse.error(40202, "Skill 未发布，无法使用")
        version_id = skill.published_version_id

    if not version_id:
        return ApiResponse.error(40203, "Skill 版本异常")

    version = db.query(SkillVersion).filter(SkillVersion.id == version_id).first()

    conv = Conversation(
        user_id=current_user.id,
        skill_id=skill.id,
        skill_version_id=version.id,
        prompt_template_id=body.prompt_template_id,
        is_test=body.is_test,
    )
    db.add(conv)
    db.flush()

    SkillActivationManager.ensure_conversation_primary_skill_event(
        conversation_id=conv.id,
        skill_id=skill.id,
        db=db,
        source=SkillActivationManager.SOURCE_MARKETPLACE,
        manual_preferred=True,
    )

    # 使用 PromptCombiner 组合三层 prompt
    combined_prompt = PromptCombiner.combine_prompts(db, conv, current_user.id)
    combined_prompt = PromptCombiner.truncate_if_needed(combined_prompt)

    sys_msg = Message(
        conversation_id=conv.id,
        role="system",
        content=combined_prompt,
        token_count=count_tokens(combined_prompt),
        parent_id=None,
        branch_index=0,
        is_active=True,
    )
    db.add(sys_msg)
    db.flush()

    welcome_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=version.welcome_message,
        token_count=count_tokens(version.welcome_message),
        parent_id=sys_msg.id,
        branch_index=0,
        is_active=True,
    )
    db.add(welcome_msg)

    sandbox_manager = SandboxFileManager()
    sandbox_result = sandbox_manager.copy_skill_directory(
        conversation_id=conv.id,
        skill_id=skill.id,
        package_path=version.package_path,
        skill_name=skill.name,
    )
    if not sandbox_result["success"]:
        logger.warning(
            "创建绑定 Skill 对话时复制技能目录失败: conversation_id=%s, skill_id=%s, message=%s",
            conv.id,
            skill.id,
            sandbox_result["message"],
        )
    else:
        sandbox_manager.sync_sandbox_to_db(conv.id, current_user.id, db)

    if not body.is_test:
        skill.use_count = (skill.use_count or 0) + 1

    db.commit()
    db.refresh(conv)
    db.refresh(welcome_msg)
    get_conversation_event_bus().publish_conversation_snapshot_nowait(
        conv=conv,
        event_type="conversation.created",
    )

    return ApiResponse.success(
        data={
            "conversation_id": conv.id,
            "skill_name": skill.name,
            "active_skills": [{"id": skill.id, "name": skill.name}],
            "prompt_template_id": conv.prompt_template_id,
            "model_provider_id": version.model_provider_id,
            "model_name": version.model_name,
            "messages": [
                {
                    "id": welcome_msg.id,
                    "role": "assistant",
                    "content": welcome_msg.content,
                    "created_at": welcome_msg.created_at.isoformat(),
                }
            ],
        }
    )


# ────── 批量操作（必须在 /{conversation_id} 路由之前注册） ──────


class _BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=1000)


class _BatchExportRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=1000)
    format: str = Field("md", pattern="^(md|docx)$")


class _BatchTagRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=1000)
    tag_id: int


@router.post("/batch-delete")
async def batch_delete(
    body: _BatchDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv_ids = [
        c.id
        for c in db.query(Conversation.id)
        .filter(Conversation.id.in_(body.ids), Conversation.user_id == current_user.id)
        .all()
    ]
    if not conv_ids:
        return ApiResponse.success(data={"deleted_count": 0})

    db.query(UsageLog).filter(UsageLog.conversation_id.in_(conv_ids)).delete(
        synchronize_session=False
    )
    db.query(WorkflowNodeConversation).filter(
        WorkflowNodeConversation.conversation_id.in_(conv_ids)
    ).delete(synchronize_session=False)
    db.query(WorkflowInstanceNodeOutput).filter(
        WorkflowInstanceNodeOutput.conversation_id.in_(conv_ids)
    ).delete(synchronize_session=False)
    deleted = (
        db.query(Conversation)
        .filter(Conversation.id.in_(conv_ids))
        .delete(synchronize_session=False)
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.error("批量删除对话失败: %s", exc)
        return ApiResponse.error(40001, "部分对话存在关联数据，无法删除")

    # 批量删除 ES 索引
    for conv_id in conv_ids:
        try:
            await search_service.delete_conversation(conv_id)
        except Exception as e:
            logger.error(f"删除索引失败 {conv_id}: {e}")
    return ApiResponse.success(data={"deleted_count": deleted})


@router.post("/batch-export")
def batch_export(
    body: _BatchExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.export_service import build_batch_export_content, export_docx

    convs = (
        db.query(Conversation)
        .filter(Conversation.id.in_(body.ids), Conversation.user_id == current_user.id)
        .all()
    )
    if not convs:
        return ApiResponse.error(40201, "未找到对话")

    valid_ids = [c.id for c in convs]
    content = build_batch_export_content(valid_ids, db)

    if body.format == "md":
        from starlette.responses import Response

        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="export_{len(valid_ids)}.md"'
            },
        )
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.close()
        export_docx(content, tmp.name)
        return FileResponse(
            tmp.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"export_{len(valid_ids)}.docx",
        )


@router.post("/batch-tag")
def batch_tag(
    body: _BatchTagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.conversation_tag import ConversationTag, ConversationTagRelation

    tag = (
        db.query(ConversationTag)
        .filter(
            ConversationTag.id == body.tag_id,
            ConversationTag.user_id == current_user.id,
        )
        .first()
    )
    if not tag:
        return ApiResponse.error(40502, "标签不存在")

    convs = (
        db.query(Conversation)
        .filter(Conversation.id.in_(body.ids), Conversation.user_id == current_user.id)
        .all()
    )
    added = 0
    for conv in convs:
        existing = (
            db.query(ConversationTagRelation)
            .filter(
                ConversationTagRelation.conversation_id == conv.id,
                ConversationTagRelation.tag_id == body.tag_id,
            )
            .first()
        )
        if not existing:
            db.add(ConversationTagRelation(conversation_id=conv.id, tag_id=body.tag_id))
            added += 1
    db.commit()
    return ApiResponse.success(data={"added_count": added})


# ────── 对话列表 ──────


@router.get("")
def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tag_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.conversation_tag import ConversationTagRelation

    query = db.query(Conversation).filter(
        Conversation.user_id == current_user.id, Conversation.is_test == False
    )
    if tag_id:
        query = query.join(
            ConversationTagRelation,
            ConversationTagRelation.conversation_id == Conversation.id,
        ).filter(ConversationTagRelation.tag_id == tag_id)

    total = query.count()
    items = (
        query.order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    conv_ids = [c.id for c in items]
    tag_rels = (
        (
            db.query(ConversationTagRelation)
            .filter(ConversationTagRelation.conversation_id.in_(conv_ids))
            .all()
        )
        if conv_ids
        else []
    )

    tags_by_conv: dict[int, list] = {}
    for r in tag_rels:
        if r.tag:
            tags_by_conv.setdefault(r.conversation_id, []).append(
                {
                    "id": r.tag.id,
                    "name": r.tag.name,
                    "color": r.tag.color,
                }
            )

    skill_ids: set[int] = set()
    conv_active_skill_ids: dict[int, list[int]] = {}
    for conv in items:
        active_ids = conv.get_active_skill_ids()
        if conv.skill_id and conv.skill_id not in active_ids:
            active_ids = [conv.skill_id] + active_ids
        conv_active_skill_ids[conv.id] = active_ids
        for sid in active_ids:
            skill_ids.add(sid)

    skill_rows = db.query(Skill.id, Skill.name).filter(Skill.id.in_(skill_ids)).all() if skill_ids else []
    skill_name_map = {row.id: row.name for row in skill_rows}

    serialized_items = []
    for conv in items:
        active_ids = conv_active_skill_ids.get(conv.id, [])
        active_skills = [
            {"id": sid, "name": skill_name_map.get(sid, f"Skill {sid}")}
            for sid in active_ids
            if sid in skill_name_map
        ]
        serialized_items.append(
            {
                "id": conv.id,
                "skill_id": conv.skill_id,
                "skill_name": build_skill_display_name(active_skills),
                "active_skills": active_skills,
                "title": conv.title or "新对话",
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "tags": tags_by_conv.get(conv.id, []),
                "live_execution": _serialize_live_execution(conv),
                "sidebar_signal": _serialize_sidebar_signal(conv),
                "sandbox_unread_change_count": int(conv.sandbox_unread_change_count or 0),
            }
        )

    return ApiResponse.success(
        data={
            "items": serialized_items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/events")
async def stream_conversation_events(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    event_bus = get_conversation_event_bus()
    pubsub = await event_bus.subscribe_user(current_user.id)
    if pubsub is None:
        return ApiResponse.error(50301, "实时事件服务暂不可用")

    heartbeat_sec = max(5, int(get_settings().CONVERSATION_EVENTS_HEARTBEAT_SEC or 15))

    async def _event_stream():
        connected_payload = {
            "type": "connected",
            "conversation_id": 0,
            "event_version": 0,
            "event_ts": datetime.now().isoformat(),
            "patch": {},
        }
        yield (
            "event: connected\n"
            f"data: {json.dumps(connected_payload, ensure_ascii=False)}\n\n"
        )
        last_heartbeat = time.monotonic()
        try:
            while True:
                if await request.is_disconnected():
                    break

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message.get("type") == "message":
                    yield f"data: {message.get('data')}\n\n"
                    last_heartbeat = time.monotonic()
                    continue

                now = time.monotonic()
                if now - last_heartbeat >= heartbeat_sec:
                    yield ": keep-alive\n\n"
                    last_heartbeat = now
        finally:
            try:
                await pubsub.unsubscribe()
            finally:
                await pubsub.aclose()

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ────── 对话详情 ──────


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: int,
    admin_view: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if admin_view and current_user.role != "admin":
        return ApiResponse.error(40301, "仅管理员可使用 admin_view 查看任意会话")

    conv_query = db.query(Conversation).filter(Conversation.id == conversation_id)
    if not admin_view:
        conv_query = conv_query.filter(Conversation.user_id == current_user.id)
    conv = conv_query.first()
    if not conv:
        return ApiResponse.error(40201, "对话不存在")
    if not admin_view:
        mark_sidebar_signal_read(db, conversation_id)
        db.refresh(conv)
        get_conversation_event_bus().publish_conversation_snapshot_nowait(
            conv=conv,
            event_type="conversation.sidebar_signal_changed",
        )

    if conv.live_message_id:
        repaired = _repair_inactive_live_message_branch(db, conv)
        if repaired:
            db.commit()
            db.refresh(conv)

    from app.services.message_tree import (
        get_active_path,
        get_sibling_count,
        get_child_branch_count,
        get_active_child_branch_index,
    )

    active_msgs = get_active_path(conversation_id, db)
    messages = [m for m in active_msgs if m.role != "system"]

    all_files = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.conversation_id == conversation_id,
            UploadedFile.message_id.isnot(None),
        )
        .all()
    )
    files_by_msg: dict[int, list] = {}
    generated_files_by_msg: dict[int, list] = {}
    for f in all_files:
        item = {
            "file_id": f.id,
            "original_name": f.original_name,
            "file_type": f.file_type,
            "file_size": f.file_size,
            "is_image": f.file_type
            in ("jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"),
        }
        if f.source == "generated":
            generated_files_by_msg.setdefault(f.message_id, []).append(item)
        else:
            files_by_msg.setdefault(f.message_id, []).append(item)

    msg_list = []
    for m in messages:
        entry = {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
            "files": files_by_msg.get(m.id, []),
            "parent_id": m.parent_id,
            "branch_index": m.branch_index,
            "sibling_count": get_sibling_count(m, db),
            "child_branch_count": get_child_branch_count(m.id, db),
            "active_child_branch_index": get_active_child_branch_index(m.id, db),
            "referenced_message_ids": m.referenced_message_ids
            if m.referenced_message_ids
            else None,
        }
        if m.role == "assistant" and m.tool_calls:
            entry["tool_calls"] = [
                {
                    "tool_call_id": tc.tool_call_id,
                    "tool_name": tc.tool_name.split("__", 1)[-1]
                    if "__" in tc.tool_name
                    else tc.tool_name,
                    "arguments": tc.arguments,
                }
                for tc in m.tool_calls
            ]
        if m.role == "assistant" and m.reasoning_content:
            entry["reasoning_content"] = m.reasoning_content
        if m.role == "tool":
            entry["tool_call_id"] = m.tool_call_id
            entry["tool_name"] = (
                m.tool_name.split("__", 1)[-1]
                if m.tool_name and "__" in m.tool_name
                else m.tool_name
            )
            entry["generated_files"] = generated_files_by_msg.get(m.id, [])
        msg_list.append(entry)

    # 查询对话标签
    from app.models.conversation_tag import ConversationTagRelation

    tag_relations = (
        db.query(ConversationTagRelation)
        .filter(ConversationTagRelation.conversation_id == conversation_id)
        .all()
    )
    tags = [
        {"id": r.tag.id, "name": r.tag.name, "color": r.tag.color}
        for r in tag_relations
        if r.tag
    ]

    # 计算当前绑定模型（优先使用对话级配置，其次 Skill 绑定）
    current_provider_id = conv.current_provider_id
    current_model_name = conv.current_model_name
    if (not current_provider_id or not current_model_name) and conv.skill_version_id:
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.id == conv.skill_version_id)
            .first()
        )
        if version and version.model_provider_id and version.model_name:
            current_provider_id = version.model_provider_id
            current_model_name = version.model_name

    skill_info = serialize_conversation_skill_info(conv, db)

    return ApiResponse.success(
        data={
            "id": conv.id,
            "skill_id": conv.skill_id,
            "skill_name": skill_info["skill_name"],
            "active_skills": skill_info["active_skills"],
            "title": conv.title or "新对话",
            "messages": msg_list,
            "current_provider_id": current_provider_id,
            "current_model_name": current_model_name,
            "tags": tags,
            "live_execution": _serialize_live_execution(conv),
            "sidebar_signal": _serialize_sidebar_signal(conv),
            "sandbox_unread_change_count": int(conv.sandbox_unread_change_count or 0),
            "detail_version": _build_live_state_detail_version(conv),
        }
    )


def _repair_inactive_live_message_branch(db: Session, conv: Conversation) -> bool:
    """修复 live_message 指向非激活分支导致刷新后消息消失的问题。"""
    if not conv.live_message_id:
        return False

    target = (
        db.query(Message)
        .filter(
            Message.id == conv.live_message_id,
            Message.conversation_id == conv.id,
        )
        .first()
    )
    if not target or target.is_active:
        return False

    changed = False
    current = target
    while current and current.conversation_id == conv.id:
        if current.is_active:
            break
        current.is_active = True
        changed = True
        if current.parent_id is None:
            break
        current = (
            db.query(Message)
            .filter(
                Message.id == current.parent_id,
                Message.conversation_id == conv.id,
            )
            .first()
        )

    return changed


@router.get("/{conversation_id}/live-state")
def get_conversation_live_state(
    conversation_id: int,
    admin_view: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if admin_view and current_user.role != "admin":
        return ApiResponse.error(40301, "仅管理员可使用 admin_view 查看任意会话")

    conv_query = db.query(Conversation).filter(Conversation.id == conversation_id)
    if not admin_view:
        conv_query = conv_query.filter(Conversation.user_id == current_user.id)
    conv = conv_query.first()
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    try:
        return ApiResponse.success(data=_serialize_live_state_snapshot(conv))
    except Exception as exc:
        # 轮询接口需要高可用，内部序列化异常时降级返回，避免前端状态机卡住
        logger.exception(
            "live-state 快照序列化失败，conversation_id=%s: %s",
            conversation_id,
            exc,
        )
        fallback_status = conv.live_status or "idle"
        fallback_payload = {
            "conversation_id": conv.id,
            "live_execution": {
                "status": fallback_status,
                "message_id": conv.live_message_id,
                "error_message": conv.live_error_message,
                "started_at": conv.live_started_at.isoformat()
                if conv.live_started_at
                else None,
                "updated_at": conv.live_updated_at.isoformat()
                if conv.live_updated_at
                else None,
            },
            "sidebar_signal": _serialize_sidebar_signal(conv),
            "sandbox_unread_change_count": int(conv.sandbox_unread_change_count or 0),
            "detail_version": json.dumps(
                {
                    "status": fallback_status,
                    "message_id": conv.live_message_id,
                    "error_message": conv.live_error_message or None,
                    "title": conv.title or "新对话",
                    "sandbox_unread_change_count": int(conv.sandbox_unread_change_count or 0),
                    "sidebar_signal_state": conv.sidebar_signal_state or "none",
                    "sidebar_signal_updated_at": (
                        conv.sidebar_signal_updated_at.isoformat()
                        if conv.sidebar_signal_updated_at
                        else None
                    ),
                    "sidebar_signal_read_at": (
                        conv.sidebar_signal_read_at.isoformat()
                        if conv.sidebar_signal_read_at
                        else None
                    ),
                    "fallback": True,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        return ApiResponse.success(data=fallback_payload)


@router.post("/{conversation_id}/sidebar-signal/read")
def mark_conversation_sidebar_signal_read(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")
    mark_sidebar_signal_read(db, conversation_id)
    db.refresh(conv)
    get_conversation_event_bus().publish_conversation_snapshot_nowait(
        conv=conv,
        event_type="conversation.sidebar_signal_changed",
    )
    return ApiResponse.success(
        data={
            "conversation_id": conversation_id,
            "sidebar_signal": _serialize_sidebar_signal(conv),
        }
    )


# ────── 修改对话标题 ──────

class CancelConversationRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=64)
    source: Optional[str] = Field(default=None, max_length=128)


@router.post("/{conversation_id}/cancel")
async def cancel_conversation_generation(
    conversation_id: int,
    request: Request,
    body: Optional[CancelConversationRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    cancel_reason = (body.reason.strip() if body and body.reason else "unspecified")[:64]
    cancel_source = (body.source.strip() if body and body.source else "unknown")[:128]

    cancelled = await get_conversation_runtime_registry().cancel(conversation_id)
    logger.info(
        "conversation.cancel.requested conversation_id=%s user_id=%s reason=%s source=%s runtime_cancelled=%s referer=%s ua=%s",
        conversation_id,
        current_user.id,
        cancel_reason,
        cancel_source,
        cancelled,
        request.headers.get("referer"),
        request.headers.get("user-agent"),
    )
    if not cancelled and conv.live_status not in ("running", "waiting_skill_confirmation"):
        return ApiResponse.success(
            data={"cancelled": False, "status": conv.live_status or "idle"}
        )

    if not cancelled and conv.live_status in ("running", "waiting_skill_confirmation"):
        engine = ConversationExecutionEngine(
            db=db,
            user_id=current_user.id,
            tool_executor=ToolExecutor(get_client_manager()),
        )
        engine.set_live_status(conversation_id, status="cancelled", error_message=None)

    return ApiResponse.success(data={"cancelled": True, "status": "cancelled"})


class _UpdateTitleRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


@router.patch("/{conversation_id}/title")
async def update_conversation_title(
    conversation_id: int,
    body: _UpdateTitleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")
    conv.title = body.title
    db.commit()
    db.refresh(conv)
    get_conversation_event_bus().publish_conversation_snapshot_nowait(
        conv=conv,
        event_type="conversation.updated",
    )
    # 同步ES
    try:
        search_service.es.update(
            index="conversations",
            id=str(conversation_id),
            body={"doc": {"title": body.title}},
            ignore=[404],
        )
    except Exception:
        pass
    return ApiResponse.success(data={"title": body.title})


@router.post("/{conversation_id}/regenerate-title")
async def regenerate_conversation_title(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    seed = _extract_title_seed_messages(db, conversation_id)
    if not seed:
        return ApiResponse.error(40001, "对话内容不足，无法生成标题")

    user_msg, ai_reply = seed
    try:
        title = await _generate_and_save_conversation_title(
            db=db,
            conv=conv,
            user_msg=user_msg,
            ai_reply=ai_reply,
        )
    except Exception as exc:
        logger.error("手动重生成标题失败: %s", exc)
        return ApiResponse.error(50001, "标题生成失败")

    if not title:
        return ApiResponse.error(50001, "标题生成失败")

    return ApiResponse.success(data={"title": title})


# ────── 删除对话 ──────


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    db.query(Message).filter(Message.conversation_id == conversation_id).delete()
    db.query(UsageLog).filter(UsageLog.conversation_id == conversation_id).delete()
    db.query(WorkflowNodeConversation).filter(
        WorkflowNodeConversation.conversation_id == conversation_id
    ).delete()
    db.query(WorkflowInstanceNodeOutput).filter(
        WorkflowInstanceNodeOutput.conversation_id == conversation_id
    ).delete()
    db.delete(conv)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.error("删除对话失败: %s", exc)
        return ApiResponse.error(40001, "对话存在关联数据，无法删除")

    # 删除 ES 索引
    try:
        await search_service.delete_conversation(conversation_id)
    except Exception as e:
        logger.error(f"删除索引失败: {e}")

    get_conversation_event_bus().publish_simple_event_nowait(
        user_id=current_user.id,
        conversation_id=conversation_id,
        event_type="conversation.deleted",
    )
    return ApiResponse.success(message="对话已删除")


# ────── 导出 ──────


class ExportRequest(BaseModel):
    format: str = Field(..., pattern="^(md|docx)$")
    scope: str = Field("last", pattern="^(last|all|message)$")
    message_id: Optional[int] = None


@router.post("/{conversation_id}/export")
def export_conversation(
    conversation_id: int,
    body: ExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.export_service import export_docx

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")
    settings = get_settings()

    all_msgs = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role.in_(["user", "assistant", "tool"]),
            Message.is_active == True,
        )
        .order_by(Message.created_at)
        .all()
    )
    if not any(m.role == "assistant" for m in all_msgs):
        return ApiResponse.error(40204, "没有可导出的 AI 回复")

    tool_results_map: dict[str, str] = {}
    for m in all_msgs:
        if m.role == "tool" and m.tool_call_id:
            preview = (m.content or "")[:200]
            tool_name = (
                (m.tool_name or "").split("__", 1)[-1] if m.tool_name else "工具"
            )
            tool_results_map[m.tool_call_id] = f"[🔧 工具调用] {tool_name} → {preview}"

    # 加载图片文件用于导出
    _IMAGE_TYPES = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}
    user_msg_ids = [m.id for m in all_msgs if m.role == "user"]
    export_file_map: dict[int, list] = {}
    if user_msg_ids:
        export_files = (
            db.query(UploadedFile)
            .filter(
                UploadedFile.message_id.in_(user_msg_ids),
                UploadedFile.file_type.in_(_IMAGE_TYPES),
            )
            .all()
        )
        for f in export_files:
            export_file_map.setdefault(f.message_id, []).append(f)

    def _format_user_images(m: Message) -> str:
        """为用户消息追加图片链接"""
        images = export_file_map.get(m.id, [])
        if not images:
            return ""
        base_url = settings.BASE_URL.rstrip("/")
        lines = [
            f"\n\n![{img.original_name}]({base_url}/api/files/image/{img.id})"
            for img in images
        ]
        return "".join(lines)

    def _format_assistant(m: Message) -> str:
        parts = []
        if m.tool_calls:
            for tc in m.tool_calls:
                display_name = (
                    tc.tool_name.split("__", 1)[-1]
                    if "__" in tc.tool_name
                    else tc.tool_name
                )
                result_text = tool_results_map.get(tc.tool_call_id, "")
                if result_text:
                    parts.append(result_text)
                else:
                    parts.append(f"[🔧 工具调用] {display_name}")
        if m.content:
            parts.append(m.content)
        return "\n\n".join(parts)

    visible_msgs = [m for m in all_msgs if m.role in ("user", "assistant")]

    if body.scope == "message" and body.message_id:
        target = next((m for m in all_msgs if m.id == body.message_id), None)
        if not target:
            return ApiResponse.error(40404, "消息不存在")
        content = (
            _format_assistant(target)
            if target.role == "assistant"
            else ((target.content or "") + _format_user_images(target))
        )
    elif body.scope == "last":
        last_ai = ""
        for m in visible_msgs:
            if m.role == "assistant":
                last_ai = _format_assistant(m)
        content = last_ai
    else:
        parts = []
        for m in visible_msgs:
            if m.role == "user":
                parts.append(f"**用户：**\n\n{m.content}{_format_user_images(m)}")
            else:
                parts.append(f"**AI：**\n\n{_format_assistant(m)}")
        content = "\n\n---\n\n".join(parts)

    skill_name = conv.skill.name if conv.skill else "自由对话"
    title = conv.title or "对话"
    date_str = datetime.now().strftime("%Y%m%d")
    base_name = f"{skill_name}_{title}_{date_str}"
    # 清理文件名中的非法字符
    base_name = "".join(
        c if c.isalnum() or c in "_-（）() " else "_" for c in base_name
    )

    scope_label = body.scope
    if body.scope == "message" and body.message_id:
        scope_label = f"message_{body.message_id}"
    export_stamp = datetime.now().strftime("%H%M%S_%f")
    artifact_name = f"{base_name}_{scope_label}_{export_stamp}"

    sandbox_saved = False
    sandbox_manager = SandboxFileManager()
    sandbox_subdir = "generated/exports"

    def _persist_export_artifact(
        *,
        ext: str,
        binary_content: bytes | None = None,
        text_content: str | None = None,
    ) -> None:
        nonlocal sandbox_saved
        filename = f"{artifact_name}.{ext}"
        sandbox_path = f"{sandbox_subdir}/{filename}"
        try:
            if ext == "md":
                result = sandbox_manager.create_file(
                    conversation_id=conversation_id,
                    filename=filename,
                    content=text_content or "",
                    subdir=sandbox_subdir,
                    overwrite=False,
                )
                file_size = len((text_content or "").encode("utf-8"))
                extracted_text = text_content or ""
            else:
                result = sandbox_manager.create_file_binary(
                    conversation_id=conversation_id,
                    filename=filename,
                    content=binary_content or b"",
                    subdir=sandbox_subdir,
                    overwrite=False,
                )
                file_size = len(binary_content or b"")
                extracted_text = None

            if not result.get("success"):
                logger.warning(
                    "导出文件保存沙箱失败: conversation_id=%s, filename=%s, message=%s",
                    conversation_id,
                    filename,
                    result.get("message"),
                )
                return

            stored_path = str(result.get("path") or "")
            if not stored_path:
                logger.warning(
                    "导出文件保存沙箱返回空路径: conversation_id=%s, filename=%s",
                    conversation_id,
                    filename,
                )
                return

            export_file = UploadedFile(
                message_id=body.message_id if body.scope == "message" else None,
                conversation_id=conversation_id,
                user_id=current_user.id,
                original_name=filename,
                stored_path=stored_path,
                file_size=file_size,
                file_type=ext,
                extracted_text=extracted_text,
                source="generated",
                sandbox_path=sandbox_path,
            )
            db.add(export_file)
            increase_sandbox_unread_change_count(db, conversation_id, delta=1)
            db.commit()
            sandbox_saved = True
        except Exception:
            db.rollback()
            logger.exception(
                "导出文件写入沙箱异常: conversation_id=%s, filename=%s",
                conversation_id,
                filename,
            )

    if body.format == "md":
        _persist_export_artifact(ext="md", text_content=content)
        encoded = quote(f"{base_name}.md")
        fallback_name = f"export_{date_str}.md"
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=\"{fallback_name}\"; filename*=UTF-8''{encoded}",
                "X-Export-Sandbox-Saved": "1" if sandbox_saved else "0",
            },
        )
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.close()
        try:
            export_docx(content, tmp.name)
            with open(tmp.name, "rb") as f:
                docx_bytes = f.read()
            _persist_export_artifact(ext="docx", binary_content=docx_bytes)
            encoded = quote(f"{base_name}.docx")
            fallback_name = f"export_{date_str}.docx"
            return FileResponse(
                path=tmp.name,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{fallback_name}\"; filename*=UTF-8''{encoded}",
                    "X-Export-Sandbox-Saved": "1" if sandbox_saved else "0",
                },
            )
        except Exception as e:
            os.unlink(tmp.name)
            return ApiResponse.error(50000, f"导出失败: {str(e)[:200]}")


# ────── 发送消息（SSE 流式，支持 Tool Call，移除 ES 推荐，支持 Skill 激活）──────


def _get_global_default_model(db: Session) -> Optional[ModelItem]:
    return (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(
            ModelProvider.is_enabled == True,
            ModelItem.is_enabled == True,
            ModelItem.is_default == True,
        )
        .first()
    )


def _get_fallback_model(db: Session) -> Optional[ModelItem]:
    default_model = _get_global_default_model(db)
    if default_model:
        return default_model
    return (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(ModelProvider.is_enabled == True, ModelItem.is_enabled == True)
        .first()
    )


def _load_mcp_tools(
    db: Session, user_role: str, skill_version: Optional[SkillVersion] = None
) -> tuple[list[dict], dict]:
    """
    加载当前可用的 MCP 工具定义。
    返回 (tools_for_llm, tool_routing_map)
    tool_routing_map: {"mcp_id__tool_name": {"mcp_id": int, "tool_name": str, ...}}
    """
    query = db.query(Mcp).filter(
        Mcp.is_enabled == True, Mcp.health_status != "circuit_open"
    )

    mcps = query.all()

    role_filter = {
        "all": ["user", "provider", "admin"],
        "provider_admin": ["provider", "admin"],
        "admin_only": ["admin"],
    }
    mcps = [m for m in mcps if user_role in role_filter.get(m.access_role, [])]

    if skill_version and skill_version.mcp_load_mode == "selected":
        bound_ids = {bm.id for bm in (skill_version.bound_mcps or [])}
        mcps = [m for m in mcps if m.id in bound_ids]

    tools_for_llm = []
    routing_map = {}

    for mcp in mcps:
        enabled_tools = [t for t in (mcp.tools or []) if t.is_enabled]
        for tool in enabled_tools:
            prefixed_name = f"{mcp.id}__{tool.tool_name}"
            tools_for_llm.append(
                {
                    "type": "function",
                    "function": {
                        "name": prefixed_name,
                        "description": tool.tool_description or "",
                        "parameters": tool.input_schema
                        or {"type": "object", "properties": {}},
                    },
                }
            )
            routing_map[prefixed_name] = {
                "mcp_id": mcp.id,
                "mcp_name": mcp.name,
                "tool_name": tool.tool_name,
                "display_name": tool.tool_name,
                "input_schema": tool.input_schema or {"type": "object", "properties": {}},
                "timeout_seconds": mcp.timeout_seconds,
                "max_retries": mcp.max_retries,
                "circuit_breaker_threshold": mcp.circuit_breaker_threshold,
                "circuit_breaker_recovery": mcp.circuit_breaker_recovery,
            }

    # 添加沙箱文件操作工具
    from app.mcp.handlers.sandbox_file_handler import get_sandbox_tools

    sandbox_tools = get_sandbox_tools()
    for tool in sandbox_tools:
        tools_for_llm.append(tool)
        # 沙箱工具不需要 routing_map，因为它们在 ConversationExecutionEngine 中特殊处理

    return tools_for_llm, routing_map


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_body = await request.body()
    body = SendMessageRequest(**json.loads(raw_body))

    settings = get_settings()

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    # 更新对话活动时间
    from datetime import datetime

    conv.last_activity_at = datetime.now()

    # 获取当前绑定的 Skill 版本
    version = None
    if conv.skill_version_id:
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.id == conv.skill_version_id)
            .first()
        )

    # 模型选择优先级：请求指定 → 智能路由(开启时) → 对话级 → Skill 绑定 → 系统默认
    routed_info = None  # (model_name, reason) if routing was used

    # 前端显式指定模型时，最高优先级
    if body.provider_id and body.model_name and not current_user.auto_route_enabled:
        provider_id = body.provider_id
        model_name = body.model_name
        # 同步更新对话绑定
        if (
            conv.current_provider_id != provider_id
            or conv.current_model_name != model_name
        ):
            conv.current_provider_id = provider_id
            conv.current_model_name = model_name
    elif current_user.auto_route_enabled and not conv.skill_id:
        # 智能路由开启且无 Skill 绑定时，优先路由
        from app.services.routing_engine import route_for_message

        routed = route_for_message(body.content, db)
        if routed:
            provider_id, model_name, reason = routed
            routed_info = (provider_id, model_name, reason)
        else:
            # 路由未命中，fallback 到对话级或系统默认
            if conv.current_provider_id and conv.current_model_name:
                provider_id = conv.current_provider_id
                model_name = conv.current_model_name
            else:
                fallback_model = _get_fallback_model(db)
                if not fallback_model:
                    return _sse_error("没有可用的模型，请联系管理员配置")
                provider_id = fallback_model.provider_id
                model_name = fallback_model.model_name
    elif conv.current_provider_id and conv.current_model_name:
        provider_id = conv.current_provider_id
        model_name = conv.current_model_name
    elif version:
        provider_id = version.model_provider_id
        model_name = version.model_name
    else:
        fallback_model = _get_fallback_model(db)
        if not fallback_model:
            return _sse_error("没有可用的模型，请联系管理员配置")
        provider_id = fallback_model.provider_id
        model_name = fallback_model.model_name

    from app.services.message_tree import get_last_active_message, build_context_path
    from app.services.compression_service import get_compressed_context

    last_active = get_last_active_message(conversation_id, db)
    parent_id = last_active.id if last_active else None

    # 自动匹配 Skill 功能已移除，不再注入 system prompt

    # 处理引用消息 ID
    ref_ids = body.referenced_message_ids
    if ref_ids and len(ref_ids) > 0:
        referenced_ids = ref_ids
    else:
        referenced_ids = None

    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=body.content,
        token_count=count_tokens(body.content),
        parent_id=parent_id,
        branch_index=0,
        is_active=True,
        referenced_message_ids=referenced_ids,
    )
    db.add(user_msg)
    db.flush()

    if body.file_ids:
        db.query(UploadedFile).filter(
            UploadedFile.id.in_(body.file_ids),
            UploadedFile.conversation_id == conversation_id,
        ).update({UploadedFile.message_id: user_msg.id}, synchronize_session=False)

    # 路由成功时，将模型绑定到对话
    if routed_info:
        conv.current_provider_id = routed_info[0]
        conv.current_model_name = routed_info[1]

    db.commit()

    is_first_user_msg = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id, Message.role == "user")
        .count()
    ) == 1

    # 使用压缩后的上下文（如果有压缩记录）
    context = build_context_path(user_msg.id, db)
    compression_summary = get_compressed_context(conversation_id, db)
    if compression_summary:
        context = [
            {"role": "system", "content": f"早期对话摘要：\n{compression_summary}"}
        ] + context[-40:]

    # 引用治理：将已选文档组装为系统上下文注入本轮推理
    reference_audit_payload = {
        "query_text": body.content,
        "selected_file_ids": [],
        "injected_chunks": [],
        "token_usage": {"reference_tokens": 0},
    }
    if body.reference_mode != "turn_only_skip":
        assembled_reference = await assemble_reference_context(
            db=db,
            conversation_id=conversation_id,
            query_text=body.content,
        )
        if assembled_reference.content:
            context.append({"role": "system", "content": assembled_reference.content})
        reference_audit_payload = {
            "query_text": body.content,
            "selected_file_ids": assembled_reference.selected_file_ids,
            "injected_chunks": assembled_reference.injected_chunks,
            "token_usage": assembled_reference.token_usage or {"reference_tokens": 0},
        }
    else:
        reference_audit_payload["token_usage"] = {
            "reference_tokens": 0,
            "mode": "turn_only_skip",
        }

    # 加载 MCP 工具
    tools_for_llm, tool_routing = _load_mcp_tools(db, current_user.role, version)

    # 添加 Skill 激活工具（允许在任何对话中激活其他技能）
    activation_tools = SkillActivationManager.generate_activation_tools(db)
    tools_for_llm.extend(activation_tools)

    tools_param = tools_for_llm if tools_for_llm else None

    # 绑定技能时，在上下文末尾追加 system 提醒以强化遵循
    if version and version.system_prompt:
        skill_name = conv.skill.name if conv.skill else ""
        if skill_name:
            context.append(
                {
                    "role": "system",
                    "content": f"【提醒】请严格遵循「{skill_name}」技能的操作流程和输出格式要求。",
                }
            )

    total_tokens = estimate_total_context(context, tools_param)
    model_item = (
        db.query(ModelItem)
        .filter_by(provider_id=provider_id, model_name=model_name)
        .first()
    )
    context_window = model_item.context_window if model_item else 65536
    context_warning = total_tokens >= int(context_window * 0.8)

    try:
        ProviderFactory.get_provider(provider_id, db)
    except ValueError as e:
        return _sse_error(str(e))

    max_tool_rounds = settings.MCP_MAX_TOOL_ROUNDS
    total_input = total_tokens
    request_user_id = current_user.id
    route_selected_payload = (
        {
            "type": "route_selected",
            "provider_id": routed_info[0],
            "model_name": routed_info[1],
            "reason": routed_info[2],
        }
        if routed_info
        else None
    )
    runtime_registry = get_conversation_runtime_registry()

    async def runner_factory(publish):
        bg_db = SessionLocal()
        bg_provider_id = provider_id
        bg_model_name = model_name
        final_content = ""

        try:
            bg_conv = (
                bg_db.query(Conversation).filter(Conversation.id == conversation_id).first()
            )
            bg_user = bg_db.query(User).filter(User.id == request_user_id).first()
            if not bg_conv or not bg_user:
                raise RuntimeError("对话上下文不存在，无法继续生成")

            if context_warning:
                await publish(
                    "context_warning", {"message": "对话较长，建议新建对话继续"}
                )
            if route_selected_payload:
                await publish("message", route_selected_payload)

            tool_executor = ToolExecutor(get_client_manager())
            engine = ConversationExecutionEngine(
                db=bg_db, user_id=request_user_id, tool_executor=tool_executor
            )
            engine.set_live_status(conversation_id, status="running", error_message=None)
            provider = ProviderFactory.get_provider(bg_provider_id, bg_db)
            mcp_config_cache = engine.build_mcp_config_cache(tool_routing)
            fallback_service = FallbackService(bg_db)

            async def call_llm(provider_instance, **kwargs):
                async for event in provider_instance.chat_completion_stream(**kwargs):
                    yield event

            async def emit(evt: dict):
                nonlocal final_content, bg_provider_id, bg_model_name
                evt_type = evt.get("type")
                if evt_type == "fallback_triggered":
                    await publish(
                        "fallback_triggered",
                        {
                            "original_model": evt.get("original_model"),
                            "error_type": evt.get("error_type"),
                            "message": f"主模型 {evt.get('original_model')} 不可用，正在切换到备用模型...",
                        },
                    )
                    return
                if evt_type == "fallback_switched":
                    fallback_model = evt.get("fallback_model") or ""
                    parts = fallback_model.split(":", 1)
                    if len(parts) == 2:
                        try:
                            bg_provider_id = int(parts[0])
                        except Exception:
                            pass
                        bg_model_name = parts[1]
                    await publish(
                        "fallback_switched",
                        {
                            "fallback_model": fallback_model,
                            "message": f"已切换到备用模型 {fallback_model}",
                        },
                    )
                    return
                if evt_type == "chunk":
                    final_content += evt.get("content", "")
                await publish("message", evt)

            async def stream_with_fallback(
                messages_for_call, current_model_name, current_tools
            ):
                async for event in fallback_service.call_with_fallback(
                    provider_id=bg_provider_id,
                    model_name=current_model_name,
                    call_func=call_llm,
                    conversation_id=conversation_id,
                    message_id=user_msg.id,
                    messages=messages_for_call,
                    temperature=0.7,
                    tools=current_tools,
                ):
                    yield event

            result = await engine.run_agent_loop(
                provider=provider,
                context=copy.deepcopy(context),
                model_name=bg_model_name,
                tools_param=copy.deepcopy(tools_param),
                tool_routing=copy.deepcopy(tool_routing),
                mcp_config_cache=mcp_config_cache,
                conversation_id=conversation_id,
                parent_message_id=user_msg.id,
                max_tool_rounds=max_tool_rounds,
                persist_logs=True,
                persist_generated_files=True,
                on_event=emit,
                stream_call=stream_with_fallback,
            )

            total_output = result.get("output_tokens", 0)
            tool_round = result.get("tool_rounds", 0)
            final_message_id = result.get("message_id")
            waiting_for_skill_confirmation = bool(
                result.get("waiting_for_skill_confirmation")
            )

            if waiting_for_skill_confirmation:
                engine.set_live_status(
                    conversation_id,
                    status="waiting_skill_confirmation",
                    message_id=final_message_id,
                    error_message=None,
                )
            else:
                engine.set_live_status(
                    conversation_id,
                    status="idle",
                    message_id=result.get("message_id"),
                    sidebar_signal_state=SIDEBAR_SIGNAL_UNREAD_REPLY,
                )

            try:
                messages = (
                    bg_db.query(Message)
                    .filter(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at)
                    .all()
                )
                msg_data = [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "created_at": m.created_at,
                    }
                    for m in messages
                ]
                bg_db.refresh(bg_conv)
                skill_info = serialize_conversation_skill_info(bg_conv, bg_db)
                await search_service.index_conversation(
                    conversation_id,
                    request_user_id,
                    bg_conv.title,
                    msg_data,
                    active_skills=skill_info["active_skills"],
                )
            except Exception as exc:
                logger.error("索引同步失败: %s", exc)

            try:
                write_reference_audit(
                    db=bg_db,
                    conversation_id=conversation_id,
                    turn_id=user_msg.id,
                    query_text=reference_audit_payload["query_text"],
                    final_selected_ids=reference_audit_payload["selected_file_ids"],
                    injected_chunks=reference_audit_payload["injected_chunks"],
                    token_usage=reference_audit_payload["token_usage"],
                    tenant_id=getattr(bg_conv, "tenant_id", None),
                )
                bg_db.commit()
            except Exception as exc:
                bg_db.rollback()
                logger.error("引用审计日志写入失败: %s", exc)

            _record_sse_generation_success(
                db=bg_db,
                current_user=bg_user,
                conv=bg_conv,
                conversation_id=conversation_id,
                provider_id=bg_provider_id,
                model_name=bg_model_name,
                total_input=total_input,
                total_output=total_output,
            )

            await publish(
                "message",
                {
                    "type": "done",
                    "message_id": final_message_id,
                    "token_usage": {
                        "input": total_input,
                        "output": total_output,
                        "total": total_input + total_output,
                    },
                    "tool_calls_count": tool_round,
                    "waiting_for_skill_confirmation": waiting_for_skill_confirmation,
                },
            )

            if is_first_user_msg and not waiting_for_skill_confirmation:
                try:
                    title = await _generate_and_save_conversation_title(
                        db=bg_db,
                        conv=bg_conv,
                        user_msg=body.content,
                        ai_reply=final_content[:200],
                        provider_id=bg_provider_id,
                        model_name=bg_model_name,
                    )
                    if title:
                        await publish("message", {"type": "title_updated", "title": title})
                except Exception:
                    pass
        except asyncio.CancelledError:
            bg_db.rollback()
            tool_executor = ToolExecutor(get_client_manager())
            cancel_engine = ConversationExecutionEngine(
                db=bg_db, user_id=request_user_id, tool_executor=tool_executor
            )
            cancel_engine.set_live_status(
                conversation_id, status="cancelled", error_message=None
            )
            await publish(
                "message",
                {"type": "cancelled", "message": "已停止当前生成任务"},
            )
            raise
        except Exception as exc:
            bg_db.rollback()
            tool_executor = ToolExecutor(get_client_manager())
            error_engine = ConversationExecutionEngine(
                db=bg_db, user_id=request_user_id, tool_executor=tool_executor
            )
            friendly_msg = _record_sse_generation_error(
                db=bg_db,
                current_user=bg_db.query(User).filter(User.id == request_user_id).first()
                or current_user,
                conv=bg_db.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
                or conv,
                conversation_id=conversation_id,
                provider_id=bg_provider_id,
                model_name=bg_model_name,
                total_input=total_input,
                error=exc,
                scene="对话生成",
            )
            error_engine.set_live_status(
                conversation_id,
                status="error",
                error_message=friendly_msg,
            )
            await publish("error", {"type": "error", "message": friendly_msg})
        finally:
            bg_db.close()

    try:
        subscriber = await runtime_registry.start(conversation_id, runner_factory)
    except RuntimeError as exc:
        return _sse_error(str(exc))

    return _runtime_streaming_response(conversation_id, subscriber)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _friendly_generation_error_message(error_message: str) -> str:
    error_lower = error_message.lower()
    if any(
        kw in error_lower
        for kw in (
            "connecterror",
            "readtimeout",
            "remoteprotocolerror",
            "connection",
            "tls",
            "ssl",
            "proxy",
            "timeout",
            "network",
        )
    ):
        return (
            "连接模型服务失败（网络抖动或超时）。系统已自动重试并尝试降级模型；"
            "如仍失败，请稍后重试或联系管理员检查模型网关。"
        )
    if any(
        kw in error_lower for kw in ("image", "multimodal", "vision", "图片", "多模态")
    ):
        return "当前模型不支持图片理解，请切换到支持多模态的模型后重试。"
    return "生成遇到问题，请重试。如持续失败请联系管理员。"


def _safe_exception_message(error: Exception) -> str:
    message = str(error or "").strip()
    if message:
        return message
    cause = getattr(error, "__cause__", None)
    if cause is not None:
        cause_message = str(cause or "").strip()
        if cause_message:
            return f"{error.__class__.__name__}: {cause_message}"
        return f"{error.__class__.__name__}: {cause.__class__.__name__}"
    return error.__class__.__name__


def _record_sse_generation_error(
    *,
    db: Session,
    current_user: User,
    conv: Conversation,
    conversation_id: int,
    provider_id: int,
    model_name: str,
    total_input: int,
    error: Exception,
    scene: str,
) -> str:
    import traceback

    error_message = _safe_exception_message(error)
    traceback_str = traceback.format_exc()
    print(f"[ERROR] {scene}失败: {error_message}")
    print(f"[TRACEBACK] {traceback_str}")

    friendly_msg = _friendly_generation_error_message(error_message)

    try:
        db.rollback()
        usage_log = UsageLog(
            user_id=current_user.id,
            skill_id=conv.skill_id,
            conversation_id=conversation_id,
            provider_id=provider_id,
            model_name=model_name,
            input_tokens=total_input,
            output_tokens=0,
            total_tokens=total_input,
            is_success=False,
            error_message=error_message[:500] if error_message else None,
        )
        db.add(usage_log)
        db.commit()
    except Exception as log_error:
        db.rollback()
        print(f"[ERROR] {scene}失败后记录 usage_log 失败: {log_error}")

    return friendly_msg


def _record_sse_generation_success(
    *,
    db: Session,
    current_user: User,
    conv: Conversation,
    conversation_id: int,
    provider_id: int,
    model_name: str,
    total_input: int,
    total_output: int,
) -> None:
    try:
        usage_log = UsageLog(
            user_id=current_user.id,
            skill_id=conv.skill_id,
            conversation_id=conversation_id,
            provider_id=provider_id,
            model_name=model_name,
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            is_success=True,
        )
        db.add(usage_log)
        db.commit()
    except Exception as log_error:
        db.rollback()
        print(f"[ERROR] 记录 usage_log 失败: {log_error}")


def _sse_error(message: str):
    async def gen():
        yield _sse_event("error", {"type": "error", "message": message})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _runtime_streaming_response(
    conversation_id: int, subscriber: asyncio.Queue
) -> StreamingResponse:
    async def generate():
        registry = get_conversation_runtime_registry()
        try:
            while True:
                item = await subscriber.get()
                event = item.get("event")
                data = item.get("data", {})
                if event == "__close__":
                    break
                yield _sse_event(event, data)
                if event == "error":
                    break
        finally:
            await registry.unsubscribe(conversation_id, subscriber)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _wait_stream_event_or_task_done(
    event_queue: asyncio.Queue, task: asyncio.Task
) -> tuple[Optional[dict], bool]:
    """等待下一条流式事件，或等待后台任务提前结束/报错，避免 SSE 挂死。"""
    event_task = asyncio.create_task(event_queue.get())
    done, pending = await asyncio.wait(
        {event_task, task}, return_when=asyncio.FIRST_COMPLETED
    )

    if event_task in done:
        return event_task.result(), False

    event_task.cancel()
    try:
        await event_task
    except asyncio.CancelledError:
        pass

    if task.done():
        exc = task.exception()
        if exc:
            raise exc
        return None, True

    return None, False


def _extract_title_seed_messages(
    db: Session, conversation_id: int
) -> Optional[tuple[str, str]]:
    messages = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role.in_(["user", "assistant"]),
        )
        .order_by(Message.created_at, Message.id)
        .all()
    )
    first_user: Optional[str] = None
    first_assistant: Optional[str] = None
    for message in messages:
        content = (message.content or "").strip()
        if not content:
            continue
        if message.role == "user" and first_user is None:
            first_user = content
            continue
        if message.role == "assistant" and first_user and first_assistant is None:
            first_assistant = content
            break
    if not first_user or not first_assistant:
        return None
    return first_user, first_assistant


def _resolve_title_model_for_conversation(
    db: Session, conv: Conversation
) -> Optional[tuple[int, str]]:
    if conv.current_provider_id and conv.current_model_name:
        return conv.current_provider_id, conv.current_model_name

    if conv.skill_version_id:
        version = (
            db.query(SkillVersion).filter(SkillVersion.id == conv.skill_version_id).first()
        )
        if version and version.model_provider_id and version.model_name:
            return version.model_provider_id, version.model_name

    fallback_model = (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(
            ModelItem.is_active == True,
            ModelProvider.is_active == True,
        )
        .order_by(ModelItem.is_default.desc(), ModelItem.id.asc())
        .first()
    )
    if not fallback_model:
        return None
    return fallback_model.provider_id, fallback_model.model_name


async def _generate_and_save_conversation_title(
    db: Session,
    conv: Conversation,
    user_msg: str,
    ai_reply: str,
    provider_id: Optional[int] = None,
    model_name: Optional[str] = None,
) -> Optional[str]:
    if not provider_id or not model_name:
        resolved = _resolve_title_model_for_conversation(db, conv)
        if not resolved:
            return None
        provider_id, model_name = resolved

    provider = ProviderFactory.get_provider(provider_id, db)
    title = await _generate_title(provider, model_name, user_msg, ai_reply)
    title = (title or "").strip()
    if not title:
        return None

    conv.title = title
    db.commit()
    db.refresh(conv)
    get_conversation_event_bus().publish_conversation_snapshot_nowait(
        conv=conv,
        event_type="conversation.updated",
    )

    try:
        search_service.es.update(
            index="conversations",
            id=str(conv.id),
            body={"doc": {"title": title}},
            ignore=[404],
        )
    except Exception:
        pass

    return title


async def _generate_title(provider, model: str, user_msg: str, ai_reply: str) -> str:
    prompt = (
        "请根据以下对话内容，生成一个简短的对话标题（不超过20个字，不要加引号和标点）：\n\n"
        f"用户：{user_msg[:200]}\n"
        f"AI：{ai_reply[:200]}\n\n"
        "请直接输出标题，不要有任何其他内容。"
    )
    content, _ = await provider.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=0.3,
        max_tokens=30,
    )
    return content.strip()[:50]


# ────── 评分反馈 ──────


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=500)


@router.post("/{conversation_id}/feedback")
def submit_feedback(
    conversation_id: int,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.feedback import Feedback

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    existing = (
        db.query(Feedback)
        .filter(
            Feedback.conversation_id == conversation_id,
            Feedback.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        existing.rating = body.rating
        existing.comment = body.comment
        db.commit()
        return ApiResponse.success(message="反馈已更新")

    fb = Feedback(
        conversation_id=conversation_id,
        user_id=current_user.id,
        skill_id=conv.skill_id,
        rating=body.rating,
        comment=body.comment,
    )
    db.add(fb)
    db.commit()
    return ApiResponse.success(message="感谢反馈")


@router.get("/{conversation_id}/feedback")
def get_feedback(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.feedback import Feedback

    fb = (
        db.query(Feedback)
        .filter(
            Feedback.conversation_id == conversation_id,
            Feedback.user_id == current_user.id,
        )
        .first()
    )
    if not fb:
        return ApiResponse.success(data=None)
    return ApiResponse.success(
        data={
            "rating": fb.rating,
            "comment": fb.comment,
        }
    )


# ────── 消息编辑与重新生成 ──────


class _EditMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    file_ids: list[int] = []
    referenced_message_ids: list[int] = []


@router.post("/{conversation_id}/messages/{msg_id}/edit")
async def edit_message(
    conversation_id: int,
    msg_id: int,
    body: _EditMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑用户消息并触发 AI 重新生成。"""
    from app.services.message_tree import (
        deactivate_subtree,
        get_next_branch_index,
        build_context_path,
    )

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    orig_msg = (
        db.query(Message)
        .filter(Message.id == msg_id, Message.conversation_id == conversation_id)
        .first()
    )
    if not orig_msg:
        return ApiResponse.error(40400, "消息不存在")
    if orig_msg.role != "user":
        return ApiResponse.error(40401, "仅用户消息可编辑")

    deactivate_subtree(orig_msg.id, db)

    new_branch = get_next_branch_index(orig_msg.parent_id, db)
    new_user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=body.content,
        token_count=count_tokens(body.content),
        referenced_message_ids=body.referenced_message_ids or [],
        parent_id=orig_msg.parent_id,
        branch_index=new_branch,
        is_active=True,
    )
    db.add(new_user_msg)
    db.flush()

    if body.file_ids:
        db.query(UploadedFile).filter(
            UploadedFile.id.in_(body.file_ids),
            UploadedFile.conversation_id == conversation_id,
        ).update({UploadedFile.message_id: new_user_msg.id}, synchronize_session=False)

    db.commit()

    context = build_context_path(new_user_msg.id, db)

    version = None
    if conv.skill_version_id:
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.id == conv.skill_version_id)
            .first()
        )
    if conv.current_provider_id and conv.current_model_name:
        provider_id = conv.current_provider_id
        model_name = conv.current_model_name
    elif version:
        provider_id = version.model_provider_id
        model_name = version.model_name
    else:
        fallback_model = _get_fallback_model(db)
        if not fallback_model:
            return _sse_error("没有可用的模型")
        provider_id = fallback_model.provider_id
        model_name = fallback_model.model_name

    tools_for_llm, tool_routing = _load_mcp_tools(db, current_user.role, version)
    tools_param = tools_for_llm if tools_for_llm else None

    try:
        ProviderFactory.get_provider(provider_id, db)
    except ValueError as e:
        return _sse_error(str(e))

    settings = get_settings()
    total_input = estimate_total_context(context, tools_param)
    runtime_registry = get_conversation_runtime_registry()
    request_user_id = current_user.id

    async def runner_factory(publish):
        bg_db = SessionLocal()
        try:
            bg_conv = (
                bg_db.query(Conversation).filter(Conversation.id == conversation_id).first()
            )
            bg_user = bg_db.query(User).filter(User.id == request_user_id).first()
            if not bg_conv or not bg_user:
                raise RuntimeError("对话上下文不存在，无法继续生成")

            tool_executor = ToolExecutor(get_client_manager())
            engine = ConversationExecutionEngine(
                db=bg_db, user_id=request_user_id, tool_executor=tool_executor
            )
            engine.set_live_status(conversation_id, status="running", error_message=None)
            bg_provider = ProviderFactory.get_provider(provider_id, bg_db)
            mcp_config_cache = engine.build_mcp_config_cache(tool_routing)

            async def emit(evt: dict):
                await publish("message", evt)

            result = await engine.run_agent_loop(
                provider=bg_provider,
                context=copy.deepcopy(context),
                model_name=model_name,
                tools_param=copy.deepcopy(tools_param),
                tool_routing=copy.deepcopy(tool_routing),
                mcp_config_cache=mcp_config_cache,
                conversation_id=conversation_id,
                parent_message_id=new_user_msg.id,
                max_tool_rounds=settings.MCP_MAX_TOOL_ROUNDS,
                on_event=emit,
            )

            waiting_for_skill_confirmation = bool(
                result.get("waiting_for_skill_confirmation")
            )
            if waiting_for_skill_confirmation:
                engine.set_live_status(
                    conversation_id,
                    status="waiting_skill_confirmation",
                    message_id=result.get("message_id"),
                    error_message=None,
                )
            else:
                engine.set_live_status(
                    conversation_id,
                    status="idle",
                    message_id=result.get("message_id"),
                    sidebar_signal_state=SIDEBAR_SIGNAL_UNREAD_REPLY,
                )

            total_output = result.get("output_tokens", 0)
            await publish(
                "message",
                {
                    "type": "done",
                    "message_id": result.get("message_id"),
                    "token_usage": {
                        "input": total_input,
                        "output": total_output,
                        "total": total_input + total_output,
                    },
                    "waiting_for_skill_confirmation": waiting_for_skill_confirmation,
                },
            )
            _record_sse_generation_success(
                db=bg_db,
                current_user=bg_user,
                conv=bg_conv,
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                total_input=total_input,
                total_output=total_output,
            )
        except asyncio.CancelledError:
            bg_db.rollback()
            cancel_engine = ConversationExecutionEngine(
                db=bg_db,
                user_id=request_user_id,
                tool_executor=ToolExecutor(get_client_manager()),
            )
            cancel_engine.set_live_status(
                conversation_id, status="cancelled", error_message=None
            )
            await publish(
                "message",
                {"type": "cancelled", "message": "已停止当前生成任务"},
            )
            raise
        except Exception as exc:
            bg_db.rollback()
            error_engine = ConversationExecutionEngine(
                db=bg_db,
                user_id=request_user_id,
                tool_executor=ToolExecutor(get_client_manager()),
            )
            friendly_msg = _record_sse_generation_error(
                db=bg_db,
                current_user=bg_db.query(User).filter(User.id == request_user_id).first()
                or current_user,
                conv=bg_db.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
                or conv,
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                total_input=total_input,
                error=exc,
                scene="编辑消息重新生成",
            )
            error_engine.set_live_status(
                conversation_id, status="error", error_message=friendly_msg
            )
            await publish("error", {"type": "error", "message": friendly_msg})
        finally:
            bg_db.close()

    try:
        subscriber = await runtime_registry.start(conversation_id, runner_factory)
    except RuntimeError as exc:
        return _sse_error(str(exc))

    return _runtime_streaming_response(conversation_id, subscriber)


@router.post("/{conversation_id}/messages/{msg_id}/regenerate")
async def regenerate_message(
    conversation_id: int,
    msg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重新生成 AI 回复（等同于内容不变的编辑）。"""
    from app.services.message_tree import (
        deactivate_subtree,
        get_next_branch_index,
        build_context_path,
    )

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    orig_msg = (
        db.query(Message)
        .filter(Message.id == msg_id, Message.conversation_id == conversation_id)
        .first()
    )
    if not orig_msg:
        return ApiResponse.error(40400, "消息不存在")
    if orig_msg.role != "assistant":
        return ApiResponse.error(40401, "仅 AI 回复可重新生成")

    deactivate_subtree(orig_msg.id, db)

    parent_msg = db.query(Message).filter(Message.id == orig_msg.parent_id).first()
    if not parent_msg:
        return ApiResponse.error(40400, "父消息不存在")

    db.commit()

    context = build_context_path(parent_msg.id, db)

    version = None
    if conv.skill_version_id:
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.id == conv.skill_version_id)
            .first()
        )
    if conv.current_provider_id and conv.current_model_name:
        provider_id = conv.current_provider_id
        model_name = conv.current_model_name
    elif version:
        provider_id = version.model_provider_id
        model_name = version.model_name
    else:
        fallback_model = _get_fallback_model(db)
        if not fallback_model:
            return _sse_error("没有可用的模型")
        provider_id = fallback_model.provider_id
        model_name = fallback_model.model_name

    tools_for_llm, tool_routing = _load_mcp_tools(db, current_user.role, version)
    tools_param = tools_for_llm if tools_for_llm else None

    try:
        ProviderFactory.get_provider(provider_id, db)
    except ValueError as e:
        return _sse_error(str(e))

    new_branch = get_next_branch_index(orig_msg.parent_id, db)

    total_input = estimate_total_context(context, tools_param)
    runtime_registry = get_conversation_runtime_registry()
    request_user_id = current_user.id
    settings = get_settings()

    async def runner_factory(publish):
        bg_db = SessionLocal()
        try:
            bg_conv = (
                bg_db.query(Conversation).filter(Conversation.id == conversation_id).first()
            )
            bg_user = bg_db.query(User).filter(User.id == request_user_id).first()
            if not bg_conv or not bg_user:
                raise RuntimeError("对话上下文不存在，无法继续生成")

            tool_executor = ToolExecutor(get_client_manager())
            engine = ConversationExecutionEngine(
                db=bg_db, user_id=request_user_id, tool_executor=tool_executor
            )
            engine.set_live_status(conversation_id, status="running", error_message=None)
            bg_provider = ProviderFactory.get_provider(provider_id, bg_db)
            mcp_config_cache = engine.build_mcp_config_cache(tool_routing)

            async def emit(evt: dict):
                await publish("message", evt)

            result = await engine.run_agent_loop(
                provider=bg_provider,
                context=copy.deepcopy(context),
                model_name=model_name,
                tools_param=copy.deepcopy(tools_param),
                tool_routing=copy.deepcopy(tool_routing),
                mcp_config_cache=mcp_config_cache,
                conversation_id=conversation_id,
                parent_message_id=orig_msg.parent_id,
                final_branch_index=new_branch,
                is_active=True,
                max_tool_rounds=settings.MCP_MAX_TOOL_ROUNDS,
                on_event=emit,
            )

            waiting_for_skill_confirmation = bool(
                result.get("waiting_for_skill_confirmation")
            )
            if waiting_for_skill_confirmation:
                engine.set_live_status(
                    conversation_id,
                    status="waiting_skill_confirmation",
                    message_id=result.get("message_id"),
                    error_message=None,
                )
            else:
                engine.set_live_status(
                    conversation_id,
                    status="idle",
                    message_id=result.get("message_id"),
                    sidebar_signal_state=SIDEBAR_SIGNAL_UNREAD_REPLY,
                )

            total_output = result.get("output_tokens", 0)
            await publish(
                "message",
                {
                    "type": "done",
                    "message_id": result.get("message_id"),
                    "token_usage": {
                        "input": total_input,
                        "output": total_output,
                        "total": total_input + total_output,
                    },
                    "waiting_for_skill_confirmation": waiting_for_skill_confirmation,
                },
            )
            _record_sse_generation_success(
                db=bg_db,
                current_user=bg_user,
                conv=bg_conv,
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                total_input=total_input,
                total_output=total_output,
            )
        except asyncio.CancelledError:
            bg_db.rollback()
            cancel_engine = ConversationExecutionEngine(
                db=bg_db,
                user_id=request_user_id,
                tool_executor=ToolExecutor(get_client_manager()),
            )
            cancel_engine.set_live_status(
                conversation_id, status="cancelled", error_message=None
            )
            await publish(
                "message",
                {"type": "cancelled", "message": "已停止当前生成任务"},
            )
            raise
        except Exception as exc:
            bg_db.rollback()
            error_engine = ConversationExecutionEngine(
                db=bg_db,
                user_id=request_user_id,
                tool_executor=ToolExecutor(get_client_manager()),
            )
            friendly_msg = _record_sse_generation_error(
                db=bg_db,
                current_user=bg_db.query(User).filter(User.id == request_user_id).first()
                or current_user,
                conv=bg_db.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
                or conv,
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                total_input=total_input,
                error=exc,
                scene="重新生成",
            )
            error_engine.set_live_status(
                conversation_id, status="error", error_message=friendly_msg
            )
            await publish("error", {"type": "error", "message": friendly_msg})
        finally:
            bg_db.close()

    try:
        subscriber = await runtime_registry.start(conversation_id, runner_factory)
    except RuntimeError as exc:
        return _sse_error(str(exc))

    return _runtime_streaming_response(conversation_id, subscriber)


@router.post("/{conversation_id}/messages/{msg_id}/continue")
async def continue_from_message(
    conversation_id: int,
    msg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从指定消息继续生成后续 AI 回复，保留该消息在上下文中的决策结果。"""
    from app.services.message_tree import (
        deactivate_descendants,
        get_next_branch_index,
        build_context_path,
    )
    from app.services.compression_service import get_compressed_context

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    resume_msg = (
        db.query(Message)
        .filter(Message.id == msg_id, Message.conversation_id == conversation_id)
        .first()
    )
    if not resume_msg:
        return ApiResponse.error(40400, "消息不存在")
    if resume_msg.role not in ("assistant", "tool"):
        return ApiResponse.error(40401, "仅 assistant/tool 消息支持继续生成")

    deactivate_descendants(resume_msg.id, db)
    db.commit()

    context = build_context_path(resume_msg.id, db)
    compression_summary = get_compressed_context(conversation_id, db)
    if compression_summary:
        context = [
            {"role": "system", "content": f"早期对话摘要：\n{compression_summary}"}
        ] + context[-40:]
    if resume_msg.role == "tool" and resume_msg.content:
        try:
            tool_payload = json.loads(resume_msg.content)
        except json.JSONDecodeError:
            tool_payload = None

        if (
            isinstance(tool_payload, dict)
            and tool_payload.get("type") == "skill_activation_rejected"
        ):
            skill_name = tool_payload.get("skill_name") or "该技能"
            context.append(
                {
                    "role": "system",
                    "content": (
                        f"用户已拒绝激活「{skill_name}」。"
                        "禁止再次尝试激活该技能。"
                        "请在不使用该技能的情况下，继续直接回答用户当前请求。"
                    ),
                }
            )

    version = None
    if conv.skill_version_id:
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.id == conv.skill_version_id)
            .first()
        )
    if conv.current_provider_id and conv.current_model_name:
        provider_id = conv.current_provider_id
        model_name = conv.current_model_name
    elif version:
        provider_id = version.model_provider_id
        model_name = version.model_name
    else:
        fallback_model = _get_fallback_model(db)
        if not fallback_model:
            return _sse_error("没有可用的模型")
        provider_id = fallback_model.provider_id
        model_name = fallback_model.model_name

    tools_for_llm, tool_routing = _load_mcp_tools(db, current_user.role, version)
    tools_param = tools_for_llm if tools_for_llm else None

    try:
        ProviderFactory.get_provider(provider_id, db)
    except ValueError as e:
        return _sse_error(str(e))

    new_branch = get_next_branch_index(resume_msg.id, db)

    total_input = estimate_total_context(context, tools_param)
    runtime_registry = get_conversation_runtime_registry()
    request_user_id = current_user.id
    settings = get_settings()

    async def runner_factory(publish):
        bg_db = SessionLocal()
        try:
            bg_conv = (
                bg_db.query(Conversation).filter(Conversation.id == conversation_id).first()
            )
            bg_user = bg_db.query(User).filter(User.id == request_user_id).first()
            if not bg_conv or not bg_user:
                raise RuntimeError("对话上下文不存在，无法继续生成")

            tool_executor = ToolExecutor(get_client_manager())
            engine = ConversationExecutionEngine(
                db=bg_db, user_id=request_user_id, tool_executor=tool_executor
            )
            engine.set_live_status(conversation_id, status="running", error_message=None)
            bg_provider = ProviderFactory.get_provider(provider_id, bg_db)
            mcp_config_cache = engine.build_mcp_config_cache(tool_routing)

            async def emit(evt: dict):
                await publish("message", evt)

            result = await engine.run_agent_loop(
                provider=bg_provider,
                context=copy.deepcopy(context),
                model_name=model_name,
                tools_param=copy.deepcopy(tools_param),
                tool_routing=copy.deepcopy(tool_routing),
                mcp_config_cache=mcp_config_cache,
                conversation_id=conversation_id,
                parent_message_id=resume_msg.id,
                final_branch_index=new_branch,
                is_active=True,
                max_tool_rounds=settings.MCP_MAX_TOOL_ROUNDS,
                on_event=emit,
            )

            waiting_for_skill_confirmation = bool(
                result.get("waiting_for_skill_confirmation")
            )
            if waiting_for_skill_confirmation:
                engine.set_live_status(
                    conversation_id,
                    status="waiting_skill_confirmation",
                    message_id=result.get("message_id"),
                    error_message=None,
                )
            else:
                engine.set_live_status(
                    conversation_id,
                    status="idle",
                    message_id=result.get("message_id"),
                    sidebar_signal_state=SIDEBAR_SIGNAL_UNREAD_REPLY,
                )

            total_output = result.get("output_tokens", 0)
            await publish(
                "message",
                {
                    "type": "done",
                    "message_id": result.get("message_id"),
                    "token_usage": {
                        "input": total_input,
                        "output": total_output,
                        "total": total_input + total_output,
                    },
                    "waiting_for_skill_confirmation": waiting_for_skill_confirmation,
                },
            )
            _record_sse_generation_success(
                db=bg_db,
                current_user=bg_user,
                conv=bg_conv,
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                total_input=total_input,
                total_output=total_output,
            )
        except asyncio.CancelledError:
            bg_db.rollback()
            cancel_engine = ConversationExecutionEngine(
                db=bg_db,
                user_id=request_user_id,
                tool_executor=ToolExecutor(get_client_manager()),
            )
            cancel_engine.set_live_status(
                conversation_id, status="cancelled", error_message=None
            )
            await publish(
                "message",
                {"type": "cancelled", "message": "已停止当前生成任务"},
            )
            raise
        except Exception as exc:
            bg_db.rollback()
            error_engine = ConversationExecutionEngine(
                db=bg_db,
                user_id=request_user_id,
                tool_executor=ToolExecutor(get_client_manager()),
            )
            friendly_msg = _record_sse_generation_error(
                db=bg_db,
                current_user=bg_db.query(User).filter(User.id == request_user_id).first()
                or current_user,
                conv=bg_db.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
                or conv,
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                total_input=total_input,
                error=exc,
                scene="继续生成",
            )
            error_engine.set_live_status(
                conversation_id, status="error", error_message=friendly_msg
            )
            await publish("error", {"type": "error", "message": friendly_msg})
        finally:
            bg_db.close()

    try:
        subscriber = await runtime_registry.start(conversation_id, runner_factory)
    except RuntimeError as exc:
        return _sse_error(str(exc))

    return _runtime_streaming_response(conversation_id, subscriber)


# ────── 对话分叉 ──────


class _ForkRequest(BaseModel):
    from_message_id: int
    content: str = Field(..., min_length=1, max_length=5000)
    file_ids: list[int] = []


@router.post("/{conversation_id}/fork")
async def fork_conversation(
    conversation_id: int,
    body: _ForkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从指定消息处分叉，创建新的对话方向。"""
    from app.services.message_tree import (
        deactivate_descendants,
        get_next_branch_index,
        build_context_path,
    )

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    fork_point = (
        db.query(Message)
        .filter(
            Message.id == body.from_message_id,
            Message.conversation_id == conversation_id,
        )
        .first()
    )
    if not fork_point:
        return ApiResponse.error(40400, "分叉消息不存在")

    deactivate_descendants(fork_point.id, db)

    new_branch = get_next_branch_index(fork_point.id, db)
    new_user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=body.content,
        token_count=count_tokens(body.content),
        parent_id=fork_point.id,
        branch_index=new_branch,
        is_active=True,
    )
    db.add(new_user_msg)
    db.flush()

    if body.file_ids:
        db.query(UploadedFile).filter(
            UploadedFile.id.in_(body.file_ids),
            UploadedFile.conversation_id == conversation_id,
        ).update({UploadedFile.message_id: new_user_msg.id}, synchronize_session=False)

    db.commit()

    context = build_context_path(new_user_msg.id, db)

    version = None
    if conv.skill_version_id:
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.id == conv.skill_version_id)
            .first()
        )
    if conv.current_provider_id and conv.current_model_name:
        provider_id = conv.current_provider_id
        model_name = conv.current_model_name
    elif version:
        provider_id = version.model_provider_id
        model_name = version.model_name
    else:
        fallback_model = _get_fallback_model(db)
        if not fallback_model:
            return _sse_error("没有可用的模型")
        provider_id = fallback_model.provider_id
        model_name = fallback_model.model_name

    tools_for_llm, tool_routing = _load_mcp_tools(db, current_user.role, version)
    tools_param = tools_for_llm if tools_for_llm else None

    try:
        ProviderFactory.get_provider(provider_id, db)
    except ValueError as e:
        return _sse_error(str(e))

    total_input = estimate_total_context(context, tools_param)
    runtime_registry = get_conversation_runtime_registry()
    request_user_id = current_user.id
    settings = get_settings()

    async def runner_factory(publish):
        bg_db = SessionLocal()
        try:
            bg_conv = (
                bg_db.query(Conversation).filter(Conversation.id == conversation_id).first()
            )
            bg_user = bg_db.query(User).filter(User.id == request_user_id).first()
            if not bg_conv or not bg_user:
                raise RuntimeError("对话上下文不存在，无法继续生成")

            tool_executor = ToolExecutor(get_client_manager())
            engine = ConversationExecutionEngine(
                db=bg_db, user_id=request_user_id, tool_executor=tool_executor
            )
            engine.set_live_status(conversation_id, status="running", error_message=None)
            bg_provider = ProviderFactory.get_provider(provider_id, bg_db)
            mcp_config_cache = engine.build_mcp_config_cache(tool_routing)

            async def emit(evt: dict):
                await publish("message", evt)

            result = await engine.run_agent_loop(
                provider=bg_provider,
                context=copy.deepcopy(context),
                model_name=model_name,
                tools_param=copy.deepcopy(tools_param),
                tool_routing=copy.deepcopy(tool_routing),
                mcp_config_cache=mcp_config_cache,
                conversation_id=conversation_id,
                parent_message_id=new_user_msg.id,
                max_tool_rounds=settings.MCP_MAX_TOOL_ROUNDS,
                on_event=emit,
            )

            waiting_for_skill_confirmation = bool(
                result.get("waiting_for_skill_confirmation")
            )
            if waiting_for_skill_confirmation:
                engine.set_live_status(
                    conversation_id,
                    status="waiting_skill_confirmation",
                    message_id=result.get("message_id"),
                    error_message=None,
                )
            else:
                engine.set_live_status(
                    conversation_id,
                    status="idle",
                    message_id=result.get("message_id"),
                    sidebar_signal_state=SIDEBAR_SIGNAL_UNREAD_REPLY,
                )

            total_output = result.get("output_tokens", 0)
            await publish(
                "message",
                {
                    "type": "done",
                    "message_id": result.get("message_id"),
                    "token_usage": {
                        "input": total_input,
                        "output": total_output,
                        "total": total_input + total_output,
                    },
                    "waiting_for_skill_confirmation": waiting_for_skill_confirmation,
                },
            )
            _record_sse_generation_success(
                db=bg_db,
                current_user=bg_user,
                conv=bg_conv,
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                total_input=total_input,
                total_output=total_output,
            )
        except asyncio.CancelledError:
            bg_db.rollback()
            cancel_engine = ConversationExecutionEngine(
                db=bg_db,
                user_id=request_user_id,
                tool_executor=ToolExecutor(get_client_manager()),
            )
            cancel_engine.set_live_status(
                conversation_id, status="cancelled", error_message=None
            )
            await publish(
                "message",
                {"type": "cancelled", "message": "已停止当前生成任务"},
            )
            raise
        except Exception as exc:
            bg_db.rollback()
            error_engine = ConversationExecutionEngine(
                db=bg_db,
                user_id=request_user_id,
                tool_executor=ToolExecutor(get_client_manager()),
            )
            friendly_msg = _record_sse_generation_error(
                db=bg_db,
                current_user=bg_db.query(User).filter(User.id == request_user_id).first()
                or current_user,
                conv=bg_db.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
                or conv,
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                total_input=total_input,
                error=exc,
                scene="对话分叉生成",
            )
            error_engine.set_live_status(
                conversation_id, status="error", error_message=friendly_msg
            )
            await publish("error", {"type": "error", "message": friendly_msg})
        finally:
            bg_db.close()

    try:
        subscriber = await runtime_registry.start(conversation_id, runner_factory)
    except RuntimeError as exc:
        return _sse_error(str(exc))

    return _runtime_streaming_response(conversation_id, subscriber)


# ────── 分支查询与切换 ──────


@router.get("/{conversation_id}/messages/{msg_id}/branches")
def get_message_branches(
    conversation_id: int,
    msg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取消息的所有同级分支列表。"""
    msg = (
        db.query(Message)
        .filter(
            Message.id == msg_id,
            Message.conversation_id == conversation_id,
        )
        .first()
    )
    if not msg:
        return ApiResponse.error(40400, "消息不存在")

    if msg.parent_id is None:
        return ApiResponse.success(
            data={
                "parent_id": None,
                "branches": [
                    {
                        "message_id": msg.id,
                        "branch_index": 0,
                        "is_active": msg.is_active,
                        "content_preview": msg.content[:100],
                        "created_at": msg.created_at.isoformat(),
                    }
                ],
                "current_branch_index": 0,
            }
        )

    siblings = (
        db.query(Message)
        .filter(Message.parent_id == msg.parent_id)
        .order_by(Message.branch_index)
        .all()
    )

    current_idx = msg.branch_index
    branches = [
        {
            "message_id": s.id,
            "branch_index": s.branch_index,
            "is_active": s.is_active,
            "content_preview": s.content[:100] if s.content else "",
            "created_at": s.created_at.isoformat(),
        }
        for s in siblings
    ]

    return ApiResponse.success(
        data={
            "parent_id": msg.parent_id,
            "branches": branches,
            "current_branch_index": current_idx,
        }
    )


class _SwitchBranchRequest(BaseModel):
    message_id: int
    branch_index: int
    parent_id: Optional[int] = None


@router.post("/{conversation_id}/switch-branch")
def switch_branch_endpoint(
    conversation_id: int,
    body: _SwitchBranchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """切换活跃分支。支持两种模式：1) message_id 推导 parent_id 2) 直接传 parent_id"""
    from app.services.message_tree import switch_branch, get_sibling_count

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    if body.parent_id:
        target_parent_id = body.parent_id
    else:
        msg = (
            db.query(Message)
            .filter(
                Message.id == body.message_id,
                Message.conversation_id == conversation_id,
            )
            .first()
        )
        if not msg or msg.parent_id is None:
            return ApiResponse.error(40400, "无法切换该消息的分支")
        target_parent_id = msg.parent_id

    active_path = switch_branch(target_parent_id, body.branch_index, db)
    db.commit()

    msg_list = []
    for m in active_path:
        if m.role == "system":
            continue
        entry = {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
            "parent_id": m.parent_id,
            "branch_index": m.branch_index,
            "sibling_count": get_sibling_count(m, db),
        }
        if m.role == "assistant" and m.tool_calls:
            entry["tool_calls"] = [
                {
                    "tool_call_id": tc.tool_call_id,
                    "tool_name": tc.tool_name.split("__", 1)[-1]
                    if "__" in tc.tool_name
                    else tc.tool_name,
                    "arguments": tc.arguments,
                }
                for tc in m.tool_calls
            ]
        if m.role == "assistant" and m.reasoning_content:
            entry["reasoning_content"] = m.reasoning_content
        msg_list.append(entry)

    return ApiResponse.success(data={"messages": msg_list})


# ────── 辅助函数 ──────

# ────── 对话级模型切换 ──────


class _SwitchModelRequest(BaseModel):
    provider_id: int
    model_name: str = Field(..., min_length=1, max_length=100)


@router.post("/{conversation_id}/switch-model")
def switch_model(
    conversation_id: int,
    body: _SwitchModelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    # 校验目标模型是否可用
    target = (
        db.query(ModelItem)
        .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
        .filter(
            ModelItem.provider_id == body.provider_id,
            ModelItem.model_name == body.model_name,
            ModelItem.is_enabled == True,
            ModelProvider.is_enabled == True,
        )
        .first()
    )
    if not target:
        return ApiResponse.error(40205, "目标模型不可用或不存在")

    provider = (
        db.query(ModelProvider).filter(ModelProvider.id == body.provider_id).first()
    )

    conv.current_provider_id = body.provider_id
    conv.current_model_name = body.model_name
    db.commit()
    db.refresh(conv)

    print(
        f"[DEBUG] 切换模型成功: conversation_id={conversation_id}, provider_id={conv.current_provider_id}, model_name={conv.current_model_name}"
    )

    notice_content = f"已切换到模型：{provider.provider_name if provider else ''} / {body.model_name}"

    return ApiResponse.success(
        data={
            "current_provider_id": conv.current_provider_id,
            "current_model_name": conv.current_model_name,
            "notice_content": notice_content,
        },
        message="模型已切换",
    )

    return ApiResponse.success(
        data={
            "current_provider_id": conv.current_provider_id,
            "current_model_name": conv.current_model_name,
            "notice_content": notice_content,
        },
        message="模型已切换",
    )


# ────── 对话标签关联 ──────


class _ConvTagRequest(BaseModel):
    tag_id: int


@router.post("/{conversation_id}/tags")
def add_conversation_tag(
    conversation_id: int,
    body: _ConvTagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.conversation_tag import ConversationTag, ConversationTagRelation
    from sqlalchemy import func

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    tag = (
        db.query(ConversationTag)
        .filter(
            ConversationTag.id == body.tag_id,
            ConversationTag.user_id == current_user.id,
        )
        .first()
    )
    if not tag:
        return ApiResponse.error(40502, "标签不存在")

    existing = (
        db.query(ConversationTagRelation)
        .filter(
            ConversationTagRelation.conversation_id == conversation_id,
            ConversationTagRelation.tag_id == body.tag_id,
        )
        .first()
    )
    if existing:
        return ApiResponse.success(message="标签已关联")

    count = (
        db.query(func.count(ConversationTagRelation.id))
        .filter(ConversationTagRelation.conversation_id == conversation_id)
        .scalar()
    ) or 0
    if count >= 5:
        return ApiResponse.error(40501, "每条对话最多关联 5 个标签")

    rel = ConversationTagRelation(conversation_id=conversation_id, tag_id=body.tag_id)
    db.add(rel)
    db.commit()

    # 同步索引到 ES
    try:
        messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .all()
        )
        if messages:
            msg_data = [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                }
                for m in messages
            ]
            skill_info = serialize_conversation_skill_info(conv, db)
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    search_service.index_conversation(
                        conversation_id,
                        current_user.id,
                        conv.title,
                        msg_data,
                        active_skills=skill_info["active_skills"],
                    )
                )
            except RuntimeError:
                asyncio.run(
                    search_service.index_conversation(
                        conversation_id,
                        current_user.id,
                        conv.title,
                        msg_data,
                        active_skills=skill_info["active_skills"],
                    )
                )
    except Exception as e:
        logger.error(f"标签操作后索引同步失败: {e}")

    return ApiResponse.success(message="标签已添加")


@router.delete("/{conversation_id}/tags/{tag_id}")
def remove_conversation_tag(
    conversation_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.conversation_tag import ConversationTagRelation

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    rel = (
        db.query(ConversationTagRelation)
        .filter(
            ConversationTagRelation.conversation_id == conversation_id,
            ConversationTagRelation.tag_id == tag_id,
        )
        .first()
    )
    if rel:
        db.delete(rel)
        db.commit()
    return ApiResponse.success(message="标签已移除")


# ────── 模型对比模式 ──────


class CompareModelsRequest(BaseModel):
    content: str
    model_a_provider_id: int
    model_a_name: str
    model_b_provider_id: int
    model_b_name: str


@router.post("/{conversation_id}/messages/compare")
async def compare_models(
    conversation_id: int,
    body: CompareModelsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """对比模式：并行调用两个模型"""
    from app.models.model_comparison import ModelComparison

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    # 获取最后一条用户消息
    from app.services.message_tree import get_last_active_message, build_context_path

    last_active = get_last_active_message(conversation_id, db)

    # 保存用户消息
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=body.content,
        parent_id=last_active.id if last_active else None,
        branch_index=0,
        is_active=True,
        created_at=datetime.now(),
    )
    db.add(user_msg)
    db.flush()

    context = build_context_path(user_msg.id, db)

    # 加载 Skill 版本和 MCP 工具
    version = None
    if conv.skill_version_id:
        version = (
            db.query(SkillVersion)
            .filter(SkillVersion.id == conv.skill_version_id)
            .first()
        )
    tools_for_llm, tool_routing = _load_mcp_tools(db, current_user.role, version)
    tools_param = tools_for_llm if tools_for_llm else None

    # 创建对比记录
    comparison = ModelComparison(
        conversation_id=conversation_id,
        user_message_id=user_msg.id,
        model_a_provider_id=body.model_a_provider_id,
        model_a_name=body.model_a_name,
        model_b_provider_id=body.model_b_provider_id,
        model_b_name=body.model_b_name,
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    async def generate():
        try:
            settings = get_settings()
            queue: asyncio.Queue = asyncio.Queue()

            async def run_side(
                side: str,
                provider_id: int,
                model_name: str,
                branch_index: int,
            ):
                side_db = SessionLocal()
                try:
                    provider = ProviderFactory.get_provider(provider_id, side_db)
                    tool_executor = ToolExecutor(get_client_manager())
                    engine = ConversationExecutionEngine(
                        db=side_db, user_id=current_user.id, tool_executor=tool_executor
                    )
                    mcp_config_cache = engine.build_mcp_config_cache(tool_routing)

                    async def side_emit(evt: dict):
                        if evt.get("type") == "done":
                            return
                        payload = dict(evt)
                        payload["side"] = side
                        await queue.put(payload)

                    result = await engine.run_agent_loop(
                        provider=provider,
                        context=copy.deepcopy(context),
                        model_name=model_name,
                        tools_param=tools_param,
                        tool_routing=tool_routing,
                        mcp_config_cache=mcp_config_cache,
                        conversation_id=conversation_id,
                        parent_message_id=user_msg.id,
                        final_branch_index=branch_index,
                        is_active=False,
                        max_tool_rounds=settings.MCP_MAX_TOOL_ROUNDS,
                        persist_logs=True,
                        persist_generated_files=False,
                        on_event=side_emit,
                    )
                    await queue.put(
                        {
                            "side": side,
                            "type": "_done",
                            "message_id": result["message_id"],
                        }
                    )
                except Exception as e:
                    await queue.put({"side": side, "type": "_error", "message": str(e)})
                finally:
                    side_db.close()

            asyncio.create_task(
                run_side("a", body.model_a_provider_id, body.model_a_name, 0)
            )
            asyncio.create_task(
                run_side("b", body.model_b_provider_id, body.model_b_name, 1)
            )

            finished = 0
            msg_a_id = None
            msg_b_id = None
            while finished < 2:
                event = await queue.get()
                et = event.get("type")
                if et == "_done":
                    finished += 1
                    if event.get("side") == "a":
                        msg_a_id = event.get("message_id")
                    else:
                        msg_b_id = event.get("message_id")
                    continue
                if et == "_error":
                    finished += 1
                    yield _sse_event(
                        "error",
                        {
                            "message": event.get("message", "模型对比失败"),
                            "side": event.get("side"),
                        },
                    )
                    continue
                yield _sse_event("message", event)

            if not msg_a_id or not msg_b_id:
                raise Exception("模型对比未产生完整结果")

            comparison.model_a_message_id = msg_a_id
            comparison.model_b_message_id = msg_b_id
            db.commit()

            yield _sse_event(
                "message",
                {
                    "type": "done",
                    "comparison_id": comparison.id,
                    "message_a_id": msg_a_id,
                    "message_b_id": msg_b_id,
                },
            )

        except Exception as e:
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/{conversation_id}/compare/{comparison_id}/choose")
def choose_comparison_winner(
    conversation_id: int,
    comparison_id: int,
    winner: str,  # 'a' or 'b'
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """选择对比结果的优胜者"""
    from app.models.model_comparison import ModelComparison

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        return ApiResponse.error(40201, "对话不存在")

    comparison = (
        db.query(ModelComparison)
        .filter(
            ModelComparison.id == comparison_id,
            ModelComparison.conversation_id == conversation_id,
        )
        .first()
    )
    if not comparison:
        return ApiResponse.error(40401, "对比记录不存在")

    if winner not in ["a", "b"]:
        return ApiResponse.error(40001, "无效的选择")

    # 更新优胜者
    comparison.winner = winner

    # 将选中的回复设为活跃分支
    chosen_msg_id = (
        comparison.model_a_message_id
        if winner == "a"
        else comparison.model_b_message_id
    )
    other_msg_id = (
        comparison.model_b_message_id
        if winner == "a"
        else comparison.model_a_message_id
    )

    if chosen_msg_id:
        chosen_msg = db.query(Message).filter(Message.id == chosen_msg_id).first()
        if chosen_msg:
            chosen_msg.is_active = True

    if other_msg_id:
        other_msg = db.query(Message).filter(Message.id == other_msg_id).first()
        if other_msg:
            other_msg.is_active = False

    # 更新对话当前模型
    if winner == "a":
        conv.current_provider_id = comparison.model_a_provider_id
        conv.current_model_name = comparison.model_a_name
    else:
        conv.current_provider_id = comparison.model_b_provider_id
        conv.current_model_name = comparison.model_b_name

    db.commit()
    return ApiResponse.success(message="已选择优胜模型")


# ────── 子路由聚合（Skill/Sandbox/Prompt Template） ──────

router.include_router(conversation_skills.router)
router.include_router(conversation_sandbox.router)
router.include_router(conversation_prompt_templates.router)
