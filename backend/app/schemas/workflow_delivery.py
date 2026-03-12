from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., min_length=1, max_length=64)
    scope: str = Field(..., pattern=r"^(PROJECT|REQUIREMENT)$")
    description: Optional[str] = None


class WorkflowVersionCreate(BaseModel):
    version_label: Optional[str] = Field(None, max_length=32)
    source_version_id: Optional[int] = Field(None, ge=1)


class WorkflowDefinitionNodeItem(BaseModel):
    node_code: str = Field(..., min_length=1, max_length=64)
    node_name: str = Field(..., min_length=1, max_length=128)
    node_order: int = Field(..., ge=1)
    skill_id: Optional[int] = Field(None, ge=1)
    input_mapping_json: Optional[dict] = None
    output_type: Optional[str] = Field(
        None,
        pattern=r"^(MARKDOWN|YUQUE_URL|MARKDOWN,YUQUE_URL|YUQUE_URL,MARKDOWN)$",
    )
    retry_policy_json: Optional[dict] = None


class WorkflowVersionNodesUpdate(BaseModel):
    nodes: list[WorkflowDefinitionNodeItem] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    level: str = Field(..., pattern=r"^(S|A|B|C|DEMAND_SET)$")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    metis_url: Optional[str] = Field(None, max_length=500)
    owner_user_ids: list[int] = Field(..., min_length=1)
    workflow_definition_id: Optional[int] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    level: Optional[str] = Field(None, pattern=r"^(S|A|B|C|DEMAND_SET)$")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    metis_url: Optional[str] = Field(None, max_length=500)


class ProjectOwnersUpdate(BaseModel):
    owner_user_ids: list[int] = Field(..., min_length=1)


class ProjectWorkflowBindingUpdate(BaseModel):
    workflow_definition_id: int = Field(..., ge=1)


class RequirementCreate(BaseModel):
    project_id: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=200)
    priority: str = Field("P2", pattern=r"^(P0|P1|P2|P3)$")
    workflow_definition_id: int = Field(..., ge=1)
    due_date: Optional[date] = None
    description: Optional[str] = None


class RequirementUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    owner_user_id: Optional[int] = Field(None, ge=1)
    priority: Optional[str] = Field(None, pattern=r"^(P0|P1|P2|P3)$")
    status: Optional[str] = Field(None, pattern=r"^(NOT_STARTED|IN_PROGRESS|COMPLETED|CANCELED)$")
    due_date: Optional[date] = None
    description: Optional[str] = None


class RequirementWorkflowBindingUpdate(BaseModel):
    workflow_definition_id: int = Field(..., ge=1)


class WorkflowInstanceCreate(BaseModel):
    scope_type: str = Field(..., pattern=r"^(PROJECT|REQUIREMENT)$")
    scope_id: int = Field(..., ge=1)
    workflow_definition_id: int = Field(..., ge=1)


class WorkflowNodeBindConversations(BaseModel):
    conversation_ids: list[int] = Field(..., min_length=1)
    binding_type: str = Field("MANUAL", pattern=r"^(AUTO|MANUAL)$")


class WorkflowNodeAdvance(BaseModel):
    to_status: str = Field(
        ...,
        pattern=r"^(PENDING|RUNNING|SUCCEEDED|FAILED|SKIPPED|BLOCKED|CANCELED)$",
    )
    note: Optional[str] = None
    skip_reason: Optional[str] = None


class WorkflowNodeOutputCreate(BaseModel):
    deliverable_type: str = Field(..., min_length=1, max_length=32)
    output_kind: str = Field("AGGREGATED", min_length=1, max_length=32)
    content_type: str = Field(..., min_length=1, max_length=32)
    content_ref: str = Field(..., min_length=1)
    conversation_id: Optional[int] = Field(None, ge=1)
    title: Optional[str] = Field(None, max_length=200)
    summary: Optional[str] = None
