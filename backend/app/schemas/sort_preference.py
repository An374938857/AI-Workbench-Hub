from pydantic import BaseModel, Field


class SortItem(BaseModel):
    id: int
    sort_order: int


class SortPreferenceUpdate(BaseModel):
    target_type: str = Field(..., pattern="^(skill|mcp|conversation)$")
    items: list[SortItem] = Field(..., min_length=1, max_length=500)


class SortPreferenceResponse(BaseModel):
    target_id: int
    sort_order: int
