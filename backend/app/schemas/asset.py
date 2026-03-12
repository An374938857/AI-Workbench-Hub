from typing import Optional

from pydantic import BaseModel, Field


class AssetCreate(BaseModel):
    scope_type: str = Field(..., pattern=r"^(PROJECT|REQUIREMENT)$")
    scope_id: int = Field(..., ge=1)
    node_code: Optional[str] = Field(None, max_length=64)
    asset_type: str = Field(..., pattern=r"^(FILE|MARKDOWN|URL|YUQUE_URL)$")
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    source_url: Optional[str] = Field(None, max_length=1000)
    file_ref: Optional[str] = Field(None, max_length=500)


class AssetRefetchResponse(BaseModel):
    id: int
    refetch_status: str
    snapshot_markdown: Optional[str] = None


class AssetUrlTitleResolveRequest(BaseModel):
    source_url: str = Field(..., max_length=1000)
