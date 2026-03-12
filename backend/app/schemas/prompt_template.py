from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class SystemPromptTemplateCreate(BaseModel):
    """创建提示词模板请求"""
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(default="role", description="分类: role/style/domain/personal")
    content: str = Field(..., min_length=1)
    priority: int = Field(default=50, ge=1, le=100)
    visibility: str = Field(default="personal", description="可见范围: personal/public")


class SystemPromptTemplateUpdate(BaseModel):
    """更新提示词模板请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = Field(None, description="分类: role/style/domain/personal")
    content: Optional[str] = Field(None, min_length=1)
    priority: Optional[int] = Field(None, ge=1, le=100)
    visibility: Optional[str] = Field(None, description="可见范围: personal/public")
    is_default: Optional[bool] = None


class SystemPromptTemplateResponse(BaseModel):
    """提示词模板响应"""
    id: int
    name: str
    category: str
    content: str
    is_default: bool
    priority: int
    is_builtin: bool
    visibility: str
    is_global_default: bool
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    is_favorited: bool = False  # 是否被当前用户收藏

    class Config:
        from_attributes = True


class PromptTemplateListResponse(BaseModel):
    """提示词模板列表响应"""
    templates: list[SystemPromptTemplateResponse]
    total: int


class SystemPromptTemplateDuplicateRequest(BaseModel):
    """复制模板请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)


class PromptTemplateStatsResponse(BaseModel):
    """模板统计信息响应"""
    conversation_count: int
    favorite_count: int
    last_used_at: Optional[datetime] = None
    version_count: int


class PromptTemplateVersionCreateRequest(BaseModel):
    """创建模板版本请求"""
    note: Optional[str] = Field(None, max_length=500)


class PromptTemplateVersionResponse(BaseModel):
    """模板版本响应"""
    id: int
    template_id: int
    version_no: int
    name: str
    category: str
    content: str
    priority: int
    visibility: str
    note: Optional[str]
    created_by: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True
