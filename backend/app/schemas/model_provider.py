from typing import Optional, List

from pydantic import BaseModel, Field


class ModelItemIn(BaseModel):
    model_name: str = Field(..., min_length=1, max_length=100)
    context_window: int = Field(..., gt=0)
    is_enabled: bool = True


class ModelProviderCreate(BaseModel):
    provider_name: str = Field(..., min_length=1, max_length=50)
    provider_key: str = Field(..., min_length=1, max_length=50)
    api_base_url: str = Field(..., min_length=1, max_length=500)
    api_key: str = Field(..., min_length=1)
    protocol_type: str = Field("openai_compatible", max_length=30)
    remark: Optional[str] = None
    models: List[ModelItemIn] = []


class ModelProviderUpdate(BaseModel):
    provider_name: Optional[str] = Field(None, max_length=50)
    api_base_url: Optional[str] = Field(None, max_length=500)
    api_key: Optional[str] = None  # 空字符串表示不修改
    protocol_type: Optional[str] = None
    remark: Optional[str] = None
    models: Optional[List[ModelItemIn]] = None


class ToggleRequest(BaseModel):
    is_enabled: bool
