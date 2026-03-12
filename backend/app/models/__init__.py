from app.models.user import User
from app.models.scene_tag import SceneTag
from app.models.skill import Skill, SkillVersion, skill_tags
from app.models.conversation import Conversation
from app.models.message import Message, MessageToolCall
from app.models.uploaded_file import UploadedFile
from app.models.model_provider import ModelProvider, ModelItem
from app.models.feedback import Feedback
from app.models.usage_log import UsageLog
from app.models.mcp import Mcp, McpTool, skill_mcps
from app.models.mcp_call_log import McpCallLog
from app.models.conversation_tag import ConversationTag, ConversationTagRelation
from app.models.user_sort_preference import UserSortPreference
from app.models.routing_rule import RoutingRule
# 新增模型
from app.models.system_prompt_template import SystemPromptTemplate
from app.models.user_prompt_favorite import UserPromptFavorite
from app.models.prompt_template_version import PromptTemplateVersion
from app.models.system_config import SystemConfig
from app.models.message_skill_event import MessageSkillEvent
from app.models.conversation_audit import (
    ConversationAuditTrace,
    ConversationAuditEvent,
    ConversationAuditArchive,
)
from app.models.project import Project, project_owners
from app.models.requirement import Requirement
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionNode,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowInstanceNodeOutput,
    WorkflowInstanceNode,
    WorkflowNodeConversation,
    WorkflowTransitionLog,
)
from app.models.asset import Asset
from app.models.reference import (
    ConversationReferenceState,
    ReferenceScopeSnapshot,
    FileLightIndex,
    ReferenceAuditLog,
    EmbeddingRebuildTask,
    EmbeddingRebuildTaskItem,
)

__all__ = [
    "User",
    "SceneTag",
    "Skill",
    "SkillVersion",
    "skill_tags",
    "Conversation",
    "Message",
    "MessageToolCall",
    "UploadedFile",
    "ModelProvider",
    "ModelItem",
    "Feedback",
    "UsageLog",
    "Mcp",
    "McpTool",
    "skill_mcps",
    "McpCallLog",
    "ConversationTag",
    "ConversationTagRelation",
    "UserSortPreference",
    "RoutingRule",
    # 新增
    "SystemPromptTemplate",
    "UserPromptFavorite",
    "PromptTemplateVersion",
    "SystemConfig",
    "MessageSkillEvent",
    "ConversationAuditTrace",
    "ConversationAuditEvent",
    "ConversationAuditArchive",
    "Project",
    "project_owners",
    "Requirement",
    "WorkflowDefinition",
    "WorkflowDefinitionVersion",
    "WorkflowDefinitionNode",
    "WorkflowInstance",
    "WorkflowInstanceNode",
    "WorkflowNodeConversation",
    "WorkflowTransitionLog",
    "WorkflowInstanceNodeOutput",
    "Asset",
    "ConversationReferenceState",
    "ReferenceScopeSnapshot",
    "FileLightIndex",
    "ReferenceAuditLog",
    "EmbeddingRebuildTask",
    "EmbeddingRebuildTaskItem",
]
