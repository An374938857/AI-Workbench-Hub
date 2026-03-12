import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.mcp import Mcp, McpTool, skill_mcps
from app.schemas.mcp import McpCreate, McpUpdate, McpToolSyncResult
from app.services.mcp.client_manager import MCPClientManager
from app.services.mcp.base_client import MCPToolInfo
from app.services.mcp.circuit_breaker import get_circuit_breaker_registry
from app.utils.crypto import encrypt_mcp_config, decrypt_mcp_config

logger = logging.getLogger(__name__)

_client_manager = MCPClientManager()


def get_client_manager() -> MCPClientManager:
    return _client_manager


def _schedule_invalidate(mcp_id: int) -> None:
    """安全地调度客户端失效，兼容同步和异步上下文"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_client_manager.invalidate(mcp_id))
    except RuntimeError:
        pass

    from app.services.mcp.circuit_breaker import get_circuit_breaker_registry
    get_circuit_breaker_registry().reset(mcp_id)


def create_mcp(db: Session, data: McpCreate, creator_id: int) -> Mcp:
    transport_type = MCPClientManager.detect_transport_type(data.config_json)
    mcp = Mcp(
        name=data.name,
        description=data.description,
        config_json_encrypted=encrypt_mcp_config(data.config_json),
        transport_type=transport_type,
        timeout_seconds=data.timeout_seconds,
        max_retries=data.max_retries,
        circuit_breaker_threshold=data.circuit_breaker_threshold,
        circuit_breaker_recovery=data.circuit_breaker_recovery,
        access_role=data.access_role,
        creator_id=creator_id,
    )
    db.add(mcp)
    db.commit()
    db.refresh(mcp)
    return mcp


def update_mcp(db: Session, mcp: Mcp, data: McpUpdate) -> Mcp:
    if data.name is not None:
        mcp.name = data.name
    if data.description is not None:
        mcp.description = data.description
    if data.config_json is not None and data.config_json != {}:
        mcp.config_json_encrypted = encrypt_mcp_config(data.config_json)
        mcp.transport_type = MCPClientManager.detect_transport_type(data.config_json)
        mcp.health_status = "unknown"
        mcp.consecutive_failures = 0
        mcp.circuit_open_until = None
        db.query(McpTool).filter(McpTool.mcp_id == mcp.id).delete()
        _schedule_invalidate(mcp.id)
    if data.timeout_seconds is not None:
        mcp.timeout_seconds = data.timeout_seconds
    if data.max_retries is not None:
        mcp.max_retries = data.max_retries
    if data.circuit_breaker_threshold is not None:
        mcp.circuit_breaker_threshold = data.circuit_breaker_threshold
    if data.circuit_breaker_recovery is not None:
        mcp.circuit_breaker_recovery = data.circuit_breaker_recovery
    if data.access_role is not None:
        mcp.access_role = data.access_role

    db.commit()
    db.refresh(mcp)
    return mcp


def delete_mcp(db: Session, mcp: Mcp) -> Optional[str]:
    """删除前检查 Skill 绑定，返回 None 表示成功，返回错误消息表示阻止"""
    bound_count = db.query(skill_mcps).filter(skill_mcps.c.mcp_id == mcp.id).count()
    if bound_count > 0:
        return f"该 MCP 正被 {bound_count} 个 Skill 绑定，请先解除绑定"

    db.query(McpTool).filter(McpTool.mcp_id == mcp.id).delete()
    db.delete(mcp)
    db.commit()
    return None


def get_decrypted_config(mcp: Mcp) -> dict:
    return decrypt_mcp_config(mcp.config_json_encrypted)


def sync_tools_from_list(db: Session, mcp_id: int, tools: list[MCPToolInfo]) -> McpToolSyncResult:
    """同步工具列表到数据库，返回变更摘要"""
    existing = {t.tool_name: t for t in db.query(McpTool).filter(McpTool.mcp_id == mcp_id).all()}
    incoming_names = {t.name for t in tools}

    added = []
    unchanged = []
    removed = []

    for tool_info in tools:
        if tool_info.name in existing:
            record = existing[tool_info.name]
            record.tool_description = tool_info.description
            record.input_schema = tool_info.input_schema
            unchanged.append(tool_info.name)
        else:
            new_tool = McpTool(
                mcp_id=mcp_id,
                tool_name=tool_info.name,
                tool_description=tool_info.description,
                input_schema=tool_info.input_schema,
            )
            db.add(new_tool)
            added.append(tool_info.name)

    for name, record in existing.items():
        if name not in incoming_names:
            db.delete(record)
            removed.append(name)

    db.commit()
    return McpToolSyncResult(added=added, removed=removed, unchanged=unchanged)


def mcp_to_list_dict(mcp: Mcp) -> dict:
    return {
        "id": mcp.id,
        "name": mcp.name,
        "description": mcp.description,
        "transport_type": mcp.transport_type,
        "is_enabled": mcp.is_enabled,
        "timeout_seconds": mcp.timeout_seconds,
        "max_retries": mcp.max_retries,
        "circuit_breaker_threshold": mcp.circuit_breaker_threshold,
        "circuit_breaker_recovery": mcp.circuit_breaker_recovery,
        "access_role": mcp.access_role,
        "health_status": mcp.health_status,
        "tool_count": len([t for t in (mcp.tools or []) if t.is_enabled]),
        "last_test_result": mcp.last_test_result,
        "last_test_time": mcp.last_test_time.isoformat() if mcp.last_test_time else None,
        "creator_name": mcp.creator.display_name if mcp.creator else "",
        "created_at": mcp.created_at.isoformat() if mcp.created_at else None,
    }


def mcp_to_detail_dict(mcp: Mcp) -> dict:
    d = mcp_to_list_dict(mcp)
    d["config_json"] = get_decrypted_config(mcp)
    d["last_test_detail"] = mcp.last_test_detail
    d["tools"] = [
        {
            "id": t.id,
            "tool_name": t.tool_name,
            "tool_description": t.tool_description,
            "input_schema": t.input_schema,
            "is_enabled": t.is_enabled,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in (mcp.tools or [])
    ]
    return d


async def run_mcp_connectivity_test(
    db: Session,
    mcp: Mcp,
    *,
    connect_timeout_seconds: int = 10,
    list_tools_timeout_seconds: int = 10,
) -> dict:
    """执行单个 MCP 连通性测试并持久化测试结果与健康状态。"""
    config_json = get_decrypted_config(mcp)
    manager = get_client_manager()
    breaker = get_circuit_breaker_registry().get_or_create(
        mcp_id=mcp.id,
        threshold=mcp.circuit_breaker_threshold,
        recovery_seconds=mcp.circuit_breaker_recovery,
    )

    start = time.monotonic()
    client = None

    try:
        client = await asyncio.wait_for(
            manager.create_temp_client(config_json, mcp.transport_type),
            timeout=connect_timeout_seconds,
        )
        tools = await asyncio.wait_for(client.list_tools(), timeout=list_tools_timeout_seconds)
        elapsed = int((time.monotonic() - start) * 1000)
        sync_result = sync_tools_from_list(db, mcp.id, tools)

        await breaker.record_success()
        mcp.last_test_result = "success"
        mcp.last_test_time = datetime.now()
        mcp.last_test_detail = f"成功获取 {len(tools)} 个工具"
        mcp.health_status = breaker.health_status
        mcp.consecutive_failures = breaker._failure_count
        mcp.circuit_open_until = breaker._open_until
        db.commit()

        return {
            "result": "success",
            "response_time_ms": elapsed,
            "tools": [{"name": t.name, "description": t.description} for t in tools],
            "tool_changes": sync_result.model_dump(),
        }
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        await breaker.record_failure()
        mcp.last_test_result = "failed"
        mcp.last_test_time = datetime.now()
        mcp.last_test_detail = str(e)
        # 连通性测试失败时，无论是否达到熔断阈值，都应标记为非正常状态。
        breaker_status = breaker.health_status
        mcp.health_status = "circuit_open" if breaker_status == "circuit_open" else "degraded"
        mcp.consecutive_failures = breaker._failure_count
        mcp.circuit_open_until = breaker._open_until
        db.commit()
        return {
            "result": "failed",
            "response_time_ms": elapsed,
            "error_detail": str(e),
        }
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


async def run_batch_connectivity_test(db: Session, mcps: list[Mcp]) -> dict:
    """批量执行 MCP 连通性测试。"""
    success_count = 0
    fail_count = 0
    details: list[dict] = []

    for mcp in mcps:
        result = await run_mcp_connectivity_test(db, mcp)
        if result["result"] == "success":
            success_count += 1
        else:
            fail_count += 1
        details.append({
            "mcp_id": mcp.id,
            "mcp_name": mcp.name,
            "result": result["result"],
            "response_time_ms": result.get("response_time_ms"),
            "error_detail": result.get("error_detail"),
        })

    return {
        "total": len(mcps),
        "success_count": success_count,
        "fail_count": fail_count,
        "details": details,
    }
