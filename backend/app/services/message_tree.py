"""消息树核心服务 — 路径回溯、分支切换、子树操作"""

import base64

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.message import Message
from app.models.uploaded_file import UploadedFile

IMAGE_TYPES = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}


def build_context_path(message_id: int, db: Session) -> list[dict]:
    """
    从指定消息沿 parent_id 回溯到根节点，构建完整的 LLM 上下文消息列表。
    如果消息包含 referenced_message_ids，会将被引用的消息插入到上下文中。
    返回按 created_at 排序的消息字典列表，格式与 LLM API 兼容。
    """
    path = _collect_path_messages(message_id, db)
    
    # 收集被引用的消息
    referenced_messages = _collect_referenced_messages(path, db)

    user_msg_ids = [m.id for m in path if m.role == "user"]
    # 也需要为被引用的消息加载文件
    user_msg_ids.extend([m.id for m in referenced_messages if m.role == "user"])
    
    file_map: dict[int, list[UploadedFile]] = {}
    if user_msg_ids:
        attached = (
            db.query(UploadedFile)
            .filter(UploadedFile.message_id.in_(user_msg_ids))
            .all()
        )
        for af in attached:
            file_map.setdefault(af.message_id, []).append(af)

    # 将被引用的消息插入到路径开头（在系统消息之后）
    # 这样 AI 会优先看到被引用的内容
    all_messages = referenced_messages + path
    
    # system prompt 去重置顶：只保留最后一个 system 消息，放在上下文第一位
    last_system = None
    non_system = []
    for m in all_messages:
        if m.role == "system":
            last_system = m
        else:
            non_system.append(m)
    ordered = ([last_system] if last_system else []) + non_system

    settings = get_settings()
    context = []
    for m in ordered:
        if m.role == "tool":
            context.append({
                "role": "tool",
                "content": m.content or "",
                "tool_call_id": m.tool_call_id or "",
            })
        elif m.role == "assistant" and m.tool_calls:
            tc_list = [
                {
                    "id": tc.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tc.tool_name,
                        "arguments": tc.arguments or "{}",
                    },
                }
                for tc in m.tool_calls
            ]
            entry: dict = {"role": "assistant", "tool_calls": tc_list}
            if m.content:
                entry["content"] = m.content
            context.append(entry)
        else:
            context.append({"role": m.role, "content": _build_message_content(m, file_map, settings)})

    return _normalize_tool_call_sequence(context)


def _normalize_tool_call_sequence(messages: list[dict]) -> list[dict]:
    """
    修复 tool call 消息序列，避免发送到 LLM 时触发 400：
    - assistant.tool_calls 后必须紧跟完整的 tool 响应（每个 tool_call_id 一条）
    - 没有前置 assistant.tool_calls 的孤立 tool 消息会被丢弃
    - 不完整 tool_calls 会降级为普通 assistant 文本消息（仅保留 content）
    """
    normalized: list[dict] = []
    i = 0
    total = len(messages)

    while i < total:
        msg = messages[i]
        role = msg.get("role")

        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg.get("tool_calls") or []
            required_ids = {
                tc.get("id")
                for tc in tool_calls
                if isinstance(tc, dict) and tc.get("id")
            }

            j = i + 1
            buffered_tools: list[dict] = []
            seen_ids: set[str] = set()
            while j < total and messages[j].get("role") == "tool":
                tool_msg = messages[j]
                tool_call_id = tool_msg.get("tool_call_id")
                if (
                    required_ids
                    and tool_call_id in required_ids
                    and tool_call_id not in seen_ids
                ):
                    buffered_tools.append(tool_msg)
                    seen_ids.add(tool_call_id)
                j += 1

            is_valid_block = bool(required_ids) and seen_ids == required_ids
            if is_valid_block:
                normalized.append(msg)
                normalized.extend(buffered_tools)
            else:
                degraded = dict(msg)
                degraded.pop("tool_calls", None)
                if degraded.get("content"):
                    normalized.append(degraded)

            i = j
            continue

        if role == "tool":
            i += 1
            continue

        normalized.append(msg)
        i += 1

    return normalized


def _build_message_content(message: Message, file_map: dict, settings) -> str | list:
    """构建消息内容，支持图片和文本文件混合。无图片时返回字符串，有图片时返回数组。"""
    text_content = message.content or ""
    image_urls: list[dict] = []

    if message.role == "user" and message.id in file_map:
        for af in file_map[message.id]:
            if af.file_type in IMAGE_TYPES:
                if settings.IMAGE_DELIVERY_MODE == "base64":
                    url = _image_to_base64_url(af.stored_path, af.file_type)
                else:
                    url = f"{settings.BASE_URL}/api/files/image/{af.id}"
                image_urls.append({"type": "image_url", "image_url": {"url": url}})
            elif af.extracted_text:
                text_content += f"\n\n[文件: {af.original_name}]\n---\n{af.extracted_text}\n---"

    if not image_urls:
        return text_content

    return [{"type": "text", "text": text_content}] + image_urls


def _image_to_base64_url(stored_path: str, file_type: str) -> str:
    """将图片文件编码为 base64 data URL"""
    with open(stored_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}
    mime = mime_map.get(file_type, f"image/{file_type}")
    return f"data:{mime};base64,{b64}"


def _collect_referenced_messages(messages: list[Message], db: Session) -> list[Message]:
    """收集所有被引用的消息"""
    referenced_ids = set()
    for msg in messages:
        if msg.referenced_message_ids:
            referenced_ids.update(msg.referenced_message_ids)
    
    if not referenced_ids:
        return []
    
    referenced = db.query(Message).filter(Message.id.in_(referenced_ids)).all()
    return sorted(referenced, key=lambda m: m.created_at)


def _collect_path_messages(message_id: int, db: Session) -> list[Message]:
    """沿 parent_id 回溯到根节点，返回按 created_at 正序排列的 Message 列表。"""
    path: list[Message] = []
    current_id: int | None = message_id

    while current_id is not None:
        msg = db.query(Message).filter(Message.id == current_id).first()
        if msg is None:
            break
        path.append(msg)
        current_id = msg.parent_id

    path.reverse()
    return path


def get_active_path(conversation_id: int, db: Session) -> list[Message]:
    """获取对话的当前活跃分支路径（所有 is_active=True 的消息按 created_at 排序）。"""
    return (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.is_active == True,
        )
        .order_by(Message.created_at)
        .all()
    )


def get_last_active_message(conversation_id: int, db: Session) -> Message | None:
    """获取对话中最后一条活跃消息（用于确定新消息的 parent_id）。"""
    return (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.is_active == True,
        )
        .order_by(Message.created_at.desc())
        .first()
    )


def deactivate_subtree(message_id: int, db: Session) -> None:
    """将指定消息及其所有后代的 is_active 设为 False（BFS 遍历）。"""
    queue = [message_id]
    while queue:
        current = queue.pop(0)
        db.query(Message).filter(Message.id == current).update(
            {"is_active": False}, synchronize_session=False
        )
        children_ids = [
            row.id
            for row in db.query(Message.id).filter(Message.parent_id == current).all()
        ]
        queue.extend(children_ids)


def deactivate_descendants(message_id: int, db: Session) -> None:
    """仅停用指定消息的后代（不包括消息本身）。"""
    children_ids = [
        row.id
        for row in db.query(Message.id).filter(Message.parent_id == message_id).all()
    ]
    for child_id in children_ids:
        deactivate_subtree(child_id, db)


def activate_branch_path(message_id: int, db: Session) -> None:
    """
    激活指定消息及其后代的默认路径。
    优先跟随已激活的子节点；若无（如刚被全部停用），则选择 branch_index 最小的子节点。
    """
    db.query(Message).filter(Message.id == message_id).update(
        {"is_active": True}, synchronize_session=False
    )
    child = (
        db.query(Message)
        .filter(Message.parent_id == message_id, Message.is_active == True)
        .first()
    )
    if not child:
        child = (
            db.query(Message)
            .filter(Message.parent_id == message_id)
            .order_by(Message.branch_index)
            .first()
        )
    if child:
        activate_branch_path(child.id, db)


def get_next_branch_index(parent_id: int | None, db: Session) -> int:
    """获取父消息下的下一个可用 branch_index。"""
    if parent_id is None:
        return 0
    max_idx = (
        db.query(func.max(Message.branch_index))
        .filter(Message.parent_id == parent_id)
        .scalar()
    )
    return (max_idx + 1) if max_idx is not None else 0


def get_sibling_count(message: Message, db: Session) -> int:
    """获取消息的同级兄弟数量（含自身）。"""
    if message.parent_id is None:
        return 1
    return (
        db.query(func.count(Message.id))
        .filter(Message.parent_id == message.parent_id)
        .scalar()
    ) or 1


def get_child_branch_count(message_id: int, db: Session) -> int:
    """
    获取消息下由「从这里继续」产生的分叉数量。
    只统计 role=user 的直接子消息数量（工具调用的中间 assistant 不算分支）。
    """
    return (
        db.query(func.count(Message.id))
        .filter(Message.parent_id == message_id, Message.role == "user")
        .scalar()
    ) or 0


def get_active_child_branch_index(message_id: int, db: Session) -> int:
    """获取消息下当前活跃的 user 子消息的 branch_index。"""
    active_child = (
        db.query(Message)
        .filter(
            Message.parent_id == message_id,
            Message.role == "user",
            Message.is_active == True,
        )
        .first()
    )
    return active_child.branch_index if active_child else 0


def switch_branch(parent_id: int, target_branch_index: int, db: Session) -> list[Message]:
    """
    切换活跃分支：
    1. 将 parent_id 下当前活跃分支的子树全部停用
    2. 将目标分支及其活跃后代路径全部激活
    3. 返回切换后从目标分支开始的活跃路径
    """
    siblings = (
        db.query(Message)
        .filter(Message.parent_id == parent_id)
        .all()
    )
    for sib in siblings:
        if sib.is_active:
            deactivate_subtree(sib.id, db)

    target = (
        db.query(Message)
        .filter(
            Message.parent_id == parent_id,
            Message.branch_index == target_branch_index,
        )
        .first()
    )
    if target:
        activate_branch_path(target.id, db)

    db.flush()

    conv_id = target.conversation_id if target else None
    if conv_id:
        return get_active_path(conv_id, db)
    return []
