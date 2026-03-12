from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.mcp import Mcp
from app.models.user import User
from app.schemas.base import ApiResponse

router = APIRouter()

ACCESS_ROLE_MAP = {
    "all": ["user", "provider", "admin"],
    "provider_admin": ["provider", "admin"],
    "admin_only": ["admin"],
}


@router.get("")
def list_mcps(
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Mcp).filter(Mcp.is_enabled == True)
    if keyword:
        query = query.filter((Mcp.name.contains(keyword)) | (Mcp.description.contains(keyword)))

    mcps = query.order_by(Mcp.created_at.desc()).all()

    items = []
    for m in mcps:
        allowed_roles = ACCESS_ROLE_MAP.get(m.access_role, [])
        if current_user.role not in allowed_roles:
            continue
        items.append({
            "id": m.id,
            "name": m.name,
            "description": m.description,
            "tool_count": len([t for t in (m.tools or []) if t.is_enabled]),
            "health_status": m.health_status,
            "last_test_result": m.last_test_result,
        })

    return ApiResponse.success(data=items)


@router.get("/{mcp_id}")
def get_mcp_detail(
    mcp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mcp = db.query(Mcp).filter(Mcp.id == mcp_id, Mcp.is_enabled == True).first()
    if not mcp:
        return ApiResponse.error(40301, "MCP 不存在或已停用")

    allowed_roles = ACCESS_ROLE_MAP.get(mcp.access_role, [])
    if current_user.role not in allowed_roles:
        return ApiResponse.error(40302, "无权限查看该 MCP")

    enabled_tools = [t for t in (mcp.tools or []) if t.is_enabled]
    return ApiResponse.success(data={
        "id": mcp.id,
        "name": mcp.name,
        "description": mcp.description,
        "tools": [
            {"name": t.tool_name, "description": t.tool_description}
            for t in enabled_tools
        ],
    })
