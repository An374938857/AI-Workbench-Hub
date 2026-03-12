from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    file_ids: list[int] = Field(default_factory=list)
    referenced_message_ids: list[int] = Field(default_factory=list)
    provider_id: int | None = None
    model_name: str | None = None
    reference_mode: str | None = None  # turn_only_skip | None


# 沙箱文件相关 Schema
class SandboxFileItem(BaseModel):
    """沙箱文件项"""
    file_id: int
    filename: str
    original_name: str
    file_size: int
    file_type: str
    source: str
    sandbox_path: Optional[str] = None
    created_at: datetime


class SandboxFileListResponse(BaseModel):
    """沙箱文件列表响应"""
    files: List[SandboxFileItem]
    total: int
    total_size: int
    sandbox_size_mb: float
    sandbox_size_limit_mb: float


class SandboxCleanupResponse(BaseModel):
    """沙箱清理响应"""
    success: bool
    message: str
    freed_size: int
    freed_size_mb: float
