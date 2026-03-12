import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.models.mcp import Mcp, McpTool
from app.models.system_config import SystemConfig
from app.models.user import User
from app.schemas.base import ApiResponse
from app.schemas.mcp import McpCreate, McpUpdate, McpToggle, McpToolToggle, McpInspectionConfigUpdate
from app.services import mcp_service
from app.services.mcp.circuit_breaker import get_circuit_breaker_registry

router = APIRouter()

MCP_INSPECTION_CONFIG_KEY = "mcp_inspection_interval_minutes"
MCP_INSPECTION_CONFIG_DESC = "MCP 自动巡检频率（分钟）"
DEFAULT_MCP_INSPECTION_INTERVAL_MINUTES = 30


# ────── MCP 列表 ──────

@router.get("")
def list_mcps(
    keyword: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    query = db.query(Mcp)
    if current_user.role != "admin":
        query = query.filter(Mcp.creator_id == current_user.id)
    if keyword:
        query = query.filter(
            (Mcp.name.contains(keyword)) | (Mcp.description.contains(keyword))
        )
    if is_enabled is not None:
        query = query.filter(Mcp.is_enabled == is_enabled)

    total = query.count()
    items = query.order_by(Mcp.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return ApiResponse.success(data={
        "items": [mcp_service.mcp_to_list_dict(m) for m in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# ────── 新增 MCP ──────

@router.post("")
def create_mcp(
    body: McpCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    try:
        mcp = mcp_service.create_mcp(db, body, current_user.id)
    except ValueError as e:
        return ApiResponse.error(40300, str(e))
    return ApiResponse.success(data=mcp_service.mcp_to_list_dict(mcp))


# ────── 自动巡检设置 ──────

@router.get("/inspection-config")
def get_inspection_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    interval_minutes = _get_inspection_interval_minutes(db)
    return ApiResponse.success(data=_format_inspection_config(interval_minutes))


@router.put("/inspection-config")
def update_inspection_config(
    body: McpInspectionConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    total_minutes = body.interval_hours * 60 + body.interval_minutes
    if total_minutes <= 0:
        return ApiResponse.error(40310, "巡检频次必须大于 0 分钟")

    config = db.query(SystemConfig).filter(SystemConfig.key == MCP_INSPECTION_CONFIG_KEY).first()
    if not config:
        config = SystemConfig(
            key=MCP_INSPECTION_CONFIG_KEY,
            description=MCP_INSPECTION_CONFIG_DESC,
        )
        db.add(config)

    config.set_value(total_minutes)
    config.updated_by = current_user.id
    db.commit()

    return ApiResponse.success(
        data=_format_inspection_config(total_minutes),
        message="巡检频次已更新",
    )


# ────── 批量连通性测试 ──────

@router.post("/batch-test")
async def batch_test_mcps(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    query = db.query(Mcp).filter(Mcp.is_enabled == True)
    if current_user.role != "admin":
        query = query.filter(Mcp.creator_id == current_user.id)
    mcps = query.order_by(Mcp.created_at.desc()).all()

    if not mcps:
        return ApiResponse.success(data={"total": 0, "success_count": 0, "fail_count": 0, "details": []})

    result = await mcp_service.run_batch_connectivity_test(db, mcps)
    return ApiResponse.success(data=result)


# ────── MCP 详情 ──────

@router.get("/{mcp_id}")
def get_mcp(
    mcp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    mcp = _get_mcp_with_access(db, mcp_id, current_user)
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在")
    return ApiResponse.success(data=mcp_service.mcp_to_detail_dict(mcp))


# ────── 编辑 MCP ──────

@router.put("/{mcp_id}")
def update_mcp(
    mcp_id: int,
    body: McpUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    mcp = _get_mcp_with_access(db, mcp_id, current_user)
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在")
    try:
        mcp = mcp_service.update_mcp(db, mcp, body)
    except ValueError as e:
        return ApiResponse.error(40300, str(e))
    return ApiResponse.success(data=mcp_service.mcp_to_detail_dict(mcp))


# ────── 删除 MCP ──────

@router.delete("/{mcp_id}")
def delete_mcp(
    mcp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    mcp = _get_mcp_with_access(db, mcp_id, current_user)
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在")
    err = mcp_service.delete_mcp(db, mcp)
    if err:
        return ApiResponse.error(40302, err)
    return ApiResponse.success(message="MCP 已删除")


# ────── 启用/停用 ──────

@router.post("/{mcp_id}/toggle")
def toggle_mcp(
    mcp_id: int,
    body: McpToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    mcp = _get_mcp_with_access(db, mcp_id, current_user)
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在")

    mcp.is_enabled = body.is_enabled
    mcp.health_status = "unknown"
    mcp.consecutive_failures = 0
    mcp.circuit_open_until = None
    db.commit()

    get_circuit_breaker_registry().reset(mcp_id)

    return ApiResponse.success(data={"is_enabled": mcp.is_enabled})


# ────── 连通性测试 ──────

@router.post("/{mcp_id}/test")
async def test_mcp(
    mcp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    mcp = _get_mcp_with_access(db, mcp_id, current_user)
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在")

    result = await mcp_service.run_mcp_connectivity_test(db, mcp)
    if result["result"] == "success":
        return ApiResponse.success(data=result)
    return ApiResponse.error(50200, "MCP 连通性测试失败", data=result)


# ────── 刷新工具列表 ──────

@router.post("/{mcp_id}/refresh-tools")
async def refresh_tools(
    mcp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    mcp = _get_mcp_with_access(db, mcp_id, current_user)
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在")

    config_json = mcp_service.get_decrypted_config(mcp)
    manager = mcp_service.get_client_manager()

    client = None
    try:
        client = await asyncio.wait_for(
            manager.create_temp_client(config_json, mcp.transport_type),
            timeout=10,
        )
        tools = await asyncio.wait_for(client.list_tools(), timeout=10)
        sync_result = mcp_service.sync_tools_from_list(db, mcp.id, tools)
        return ApiResponse.success(data=sync_result.model_dump())
    except Exception as e:
        return ApiResponse.error(50201, f"刷新工具列表失败: {e}")
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


# ────── 获取工具列表 ──────

@router.get("/{mcp_id}/tools")
def get_tools(
    mcp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    mcp = _get_mcp_with_access(db, mcp_id, current_user)
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在")

    tools = db.query(McpTool).filter(McpTool.mcp_id == mcp_id).order_by(McpTool.tool_name).all()
    return ApiResponse.success(data=[
        {
            "id": t.id,
            "tool_name": t.tool_name,
            "tool_description": t.tool_description,
            "input_schema": t.input_schema,
            "is_enabled": t.is_enabled,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in tools
    ])


# ────── 启停单个工具 ──────

@router.put("/{mcp_id}/tools/{tool_id}/toggle")
def toggle_tool(
    mcp_id: int,
    tool_id: int,
    body: McpToolToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("provider", "admin")),
):
    mcp = _get_mcp_with_access(db, mcp_id, current_user)
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在")

    tool = db.query(McpTool).filter(McpTool.id == tool_id, McpTool.mcp_id == mcp_id).first()
    if not tool:
        return ApiResponse.error(40303, "工具不存在")

    tool.is_enabled = body.is_enabled
    db.commit()
    return ApiResponse.success(data={"is_enabled": tool.is_enabled})


# ────── 辅助函数 ──────

def _get_mcp_with_access(db: Session, mcp_id: int, user: User) -> Optional[Mcp]:
    mcp = db.query(Mcp).filter(Mcp.id == mcp_id).first()
    if not mcp:
        return None
    if user.role != "admin" and mcp.creator_id != user.id:
        return None
    return mcp


def _get_inspection_interval_minutes(db: Session) -> int:
    config = db.query(SystemConfig).filter(SystemConfig.key == MCP_INSPECTION_CONFIG_KEY).first()
    if not config:
        return DEFAULT_MCP_INSPECTION_INTERVAL_MINUTES
    value = config.get_value()
    if not isinstance(value, int) or value <= 0:
        return DEFAULT_MCP_INSPECTION_INTERVAL_MINUTES
    return value


def _format_inspection_config(total_minutes: int) -> dict:
    return {
        "interval_total_minutes": total_minutes,
        "interval_hours": total_minutes // 60,
        "interval_minutes": total_minutes % 60,
    }
