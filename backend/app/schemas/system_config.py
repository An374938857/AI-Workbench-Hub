from typing import Optional, Any
from pydantic import BaseModel


class SystemConfigUpdate(BaseModel):
    """系统配置更新请求"""
    key: str
    value: Any
    description: Optional[str] = None


class SystemConfigResponse(BaseModel):
    """系统配置响应"""
    id: int
    key: str
    value: Optional[str]
    value_type: str
    description: Optional[str]
    updated_by: Optional[int]
    updated_at: str

    class Config:
        from_attributes = True