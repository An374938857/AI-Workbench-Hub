from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ==================== MCP 管理 ====================

class McpCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    config_json: dict = Field(..., description="MCP JSON 配置")
    timeout_seconds: int = Field(30, ge=5, le=120)
    max_retries: int = Field(0, ge=0, le=3)
    circuit_breaker_threshold: int = Field(5, ge=1, le=100)
    circuit_breaker_recovery: int = Field(300, ge=10, le=3600)
    access_role: str = Field("all", pattern=r"^(all|provider_admin|admin_only)$")


class McpUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    config_json: Optional[dict] = Field(None, description="传空对象 {} 表示不修改")
    timeout_seconds: Optional[int] = Field(None, ge=5, le=120)
    max_retries: Optional[int] = Field(None, ge=0, le=3)
    circuit_breaker_threshold: Optional[int] = Field(None, ge=1, le=100)
    circuit_breaker_recovery: Optional[int] = Field(None, ge=10, le=3600)
    access_role: Optional[str] = Field(None, pattern=r"^(all|provider_admin|admin_only)$")


class McpToggle(BaseModel):
    is_enabled: bool


class McpToolToggle(BaseModel):
    is_enabled: bool


class McpInspectionConfigUpdate(BaseModel):
    interval_hours: int = Field(0, ge=0, le=168)
    interval_minutes: int = Field(30, ge=0, le=59)


# ==================== MCP 响应 ====================

class McpToolResponse(BaseModel):
    id: int
    tool_name: str
    tool_description: Optional[str] = None
    input_schema: Optional[dict] = None
    is_enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class McpListResponse(BaseModel):
    """后台管理列表用"""
    id: int
    name: str
    description: str
    transport_type: str
    is_enabled: bool
    timeout_seconds: int
    max_retries: int
    circuit_breaker_threshold: int
    circuit_breaker_recovery: int
    access_role: str
    health_status: str
    tool_count: int = 0
    last_test_result: Optional[str] = None
    last_test_time: Optional[datetime] = None
    creator_name: str = ""
    created_at: datetime


class McpDetailResponse(McpListResponse):
    """后台管理详情用，含 JSON 配置"""
    config_json: dict = {}
    last_test_detail: Optional[str] = None
    tools: list[McpToolResponse] = []


class McpPublicResponse(BaseModel):
    """前台广场列表用，不含敏感信息"""
    id: int
    name: str
    description: str
    tool_count: int = 0
    health_status: str = "unknown"


class McpPublicDetailResponse(BaseModel):
    """前台广场详情用"""
    id: int
    name: str
    description: str
    tools: list["McpToolPublicResponse"] = []


class McpToolPublicResponse(BaseModel):
    """前台展示的工具信息，仅名称和描述"""
    name: str
    description: Optional[str] = None


# ==================== 连通性测试 ====================

class McpTestResult(BaseModel):
    result: str  # success / failed
    response_time_ms: Optional[int] = None
    tools: Optional[list[McpToolPublicResponse]] = None
    tool_changes: Optional[dict] = None
    error_detail: Optional[str] = None


# ==================== 工具刷新 ====================

class McpToolSyncResult(BaseModel):
    added: list[str] = []
    removed: list[str] = []
    unchanged: list[str] = []


# ==================== MCP 调用日志 ====================

class McpCallLogResponse(BaseModel):
    id: int
    user_id: int
    conversation_id: int
    mcp_id: int
    tool_name: str
    tool_call_id: str
    arguments: Optional[str] = None
    result: Optional[str] = None
    is_success: bool
    error_message: Optional[str] = None
    response_time_ms: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ==================== 数据看板 MCP 维度 ====================

class McpOverviewResponse(BaseModel):
    total_mcps: int
    enabled_mcps: int
    total_tool_calls: int
    today_tool_calls: int
    tool_call_success_rate: float
    avg_response_time_ms: float


class McpStatResponse(BaseModel):
    mcp_id: int
    mcp_name: str
    call_count: int
    success_rate: float
    avg_response_time_ms: float
    last_called_at: Optional[datetime] = None


class ToolRankingResponse(BaseModel):
    tool_name: str
    mcp_name: str
    call_count: int
