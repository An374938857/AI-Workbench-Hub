from typing import Optional, List

from pydantic import BaseModel, Field


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    icon_emoji: Optional[str] = Field(None, max_length=10)
    brief_desc: str = Field(..., min_length=1, max_length=1000)
    detail_desc: str = Field(..., min_length=1)
    tag_ids: List[int] = []
    system_prompt: str = Field(..., min_length=1)
    welcome_message: str = Field(..., min_length=1)
    model_provider_id: int
    model_name: str = Field(..., min_length=1, max_length=100)
    usage_example: Optional[str] = None
    temp_package_id: Optional[str] = None
    mcp_load_mode: str = Field("all", pattern=r"^(all|selected)$")
    mcp_ids: Optional[List[int]] = None


class SkillUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    icon_emoji: Optional[str] = Field(None, max_length=10)
    brief_desc: Optional[str] = Field(None, max_length=1000)
    detail_desc: Optional[str] = None
    tag_ids: Optional[List[int]] = None
    system_prompt: Optional[str] = None
    welcome_message: Optional[str] = None
    model_provider_id: Optional[int] = None
    model_name: Optional[str] = None
    usage_example: Optional[str] = None
    mcp_load_mode: Optional[str] = Field(None, pattern=r"^(all|selected)$")
    mcp_ids: Optional[List[int]] = None


class PublishRequest(BaseModel):
    change_log: str = Field(..., min_length=1, max_length=500)
