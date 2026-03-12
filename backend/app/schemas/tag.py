from typing import Optional

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field("#409eff", pattern=r"^#[0-9a-fA-F]{6}$")


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: Optional[int] = Field(None, ge=0)


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    sort_order: int
    conversation_count: int = 0


class ConversationTagRequest(BaseModel):
    tag_id: int
