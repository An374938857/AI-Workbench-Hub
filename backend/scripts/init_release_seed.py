"""Initialize release seed data (idempotent) for open-source bootstrap."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.database import SessionLocal
from app.models.conversation import Conversation
from app.models.mcp import Mcp, McpTool
from app.models.message import Message
from app.models.model_provider import ModelItem, ModelProvider
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.scene_tag import SceneTag
from app.models.skill import Skill, SkillVersion
from app.models.system_prompt_template import SystemPromptTemplate
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionNode,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowInstanceNode,
    WorkflowNodeConversation,
)
from app.services.mcp.client_manager import MCPClientManager
from app.utils.crypto import encrypt_api_key, encrypt_mcp_config


SEED_ROOT = Path(__file__).resolve().parent.parent / "seeds" / "release"
SEED_SKILL_PACKAGE_ROOT = "./seed_skill_packages"
AUTH_PLACEHOLDER = "<REQUIRED>"
SEED_ICON_DIR = SEED_ROOT / "icons"
SKILL_ICON_FILENAME_BY_NAME = {
    "docx": "16_83032e85.png",
    "xlsx": "17_2677fe2d.png",
    "pptx": "18_a53a3cf3.png",
    "pdf": "19_756afc3a.png",
}


def _load_seed_file(filename: str) -> list[dict[str, Any]]:
    path = SEED_ROOT / filename
    if not path.exists():
        print(f"seed file not found, skip: {path}")
        return []
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, list) else []


def _get_seed_owner_id(db: Session) -> int:
    admin = db.query(User).filter(User.username == "admin").first()
    if admin:
        return admin.id
    any_admin = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
    if any_admin:
        return any_admin.id
    fallback_user = db.query(User).order_by(User.id.asc()).first()
    if fallback_user:
        return fallback_user.id
    raise RuntimeError("no user found, please run init_admin.py first")


def _sanitize_sensitive_values(config: Any) -> Any:
    if isinstance(config, dict):
        sanitized: dict[str, Any] = {}
        for key, value in config.items():
            normalized_key = key.lower()
            if normalized_key in {"authorization", "api_key", "apikey", "token", "access_token", "bearer_token"} and isinstance(value, str):
                sanitized[key] = AUTH_PLACEHOLDER
            else:
                sanitized[key] = _sanitize_sensitive_values(value)
        return sanitized
    if isinstance(config, list):
        sanitized_list: list[Any] = []
        for idx, item in enumerate(config):
            if isinstance(item, str):
                prev = config[idx - 1] if idx > 0 else None
                if isinstance(prev, str) and prev.lower() in {"--api-key", "--apikey", "--token", "-k"}:
                    sanitized_list.append(AUTH_PLACEHOLDER)
                    continue
                if item.startswith("sk-") or item.startswith("ctx7sk-"):
                    sanitized_list.append(AUTH_PLACEHOLDER)
                    continue
            sanitized_list.append(_sanitize_sensitive_values(item))
        return sanitized_list
    return config


def _normalize_json_value(raw_value: Any) -> Any:
    if not isinstance(raw_value, str):
        return raw_value
    value = raw_value.strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return raw_value


def _upsert_model_providers(
    db: Session,
    owner_id: int,
    providers: list[dict[str, Any]],
) -> tuple[dict[int, int], int]:
    source_id_map: dict[int, int] = {}
    upsert_count = 0

    for item in providers:
        provider_key = str(item.get("provider_key") or "").strip()
        if not provider_key:
            continue

        source_id = int(item.get("source_id") or 0)
        provider = db.query(ModelProvider).filter(ModelProvider.provider_key == provider_key).first()
        provider_key = str(item.get("provider_key") or "").strip()
        env_var_name = str(item.get("api_key_env") or "").strip()
        env_api_key = os.getenv(env_var_name) if env_var_name else None
        if not env_api_key and provider_key == "aliyun":
            env_api_key = os.getenv("RELEASE_ALIYUN_CODING_PLAN_API_KEY")
        api_key_raw = str(env_api_key or item.get("api_key_placeholder") or AUTH_PLACEHOLDER)
        encrypted_key = encrypt_api_key(api_key_raw)

        if not provider:
            provider = ModelProvider(
                provider_name=str(item.get("provider_name") or provider_key),
                provider_key=provider_key,
                api_base_url=str(item.get("api_base_url") or ""),
                api_key_encrypted=encrypted_key,
                protocol_type=str(item.get("protocol_type") or "openai_compatible"),
                is_enabled=bool(item.get("is_enabled", True)),
                remark=item.get("remark"),
            )
            db.add(provider)
            db.flush()
            upsert_count += 1
        else:
            provider.provider_name = str(item.get("provider_name") or provider.provider_name)
            provider.api_base_url = str(item.get("api_base_url") or provider.api_base_url)
            provider.api_key_encrypted = encrypted_key
            provider.protocol_type = str(item.get("protocol_type") or provider.protocol_type)
            provider.is_enabled = bool(item.get("is_enabled", provider.is_enabled))
            provider.remark = item.get("remark")
            upsert_count += 1

        if source_id > 0:
            source_id_map[source_id] = provider.id

    return source_id_map, upsert_count


def _upsert_model_items(
    db: Session,
    source_provider_id_map: dict[int, int],
    model_items_seed: list[dict[str, Any]],
) -> int:
    upsert_count = 0
    for item in model_items_seed:
        source_provider_id = int(item.get("source_provider_id") or 0)
        target_provider_id = source_provider_id_map.get(source_provider_id)
        if not target_provider_id:
            continue

        existing_models = {
            model.model_name: model
            for model in db.query(ModelItem).filter(ModelItem.provider_id == target_provider_id).all()
        }
        incoming_model_names = set()
        has_default = False
        for model_payload in item.get("models") or []:
            model_name = str(model_payload.get("model_name") or "").strip()
            if not model_name:
                continue
            incoming_model_names.add(model_name)
            is_default = bool(model_payload.get("is_default", False))
            has_default = has_default or is_default

            model = existing_models.get(model_name)
            if not model:
                model = ModelItem(
                    provider_id=target_provider_id,
                    model_name=model_name,
                    context_window=int(model_payload.get("context_window") or 128000),
                    is_enabled=bool(model_payload.get("is_enabled", True)),
                    is_default=is_default,
                    capability_tags=model_payload.get("capability_tags"),
                    speed_rating=model_payload.get("speed_rating"),
                    cost_rating=model_payload.get("cost_rating"),
                    description=model_payload.get("description"),
                    max_output_tokens=model_payload.get("max_output_tokens"),
                )
                db.add(model)
            else:
                model.context_window = int(model_payload.get("context_window") or model.context_window or 128000)
                model.is_enabled = bool(model_payload.get("is_enabled", model.is_enabled))
                model.is_default = is_default
                model.capability_tags = model_payload.get("capability_tags")
                model.speed_rating = model_payload.get("speed_rating")
                model.cost_rating = model_payload.get("cost_rating")
                model.description = model_payload.get("description")
                model.max_output_tokens = model_payload.get("max_output_tokens")
            upsert_count += 1

        if incoming_model_names:
            for model_name, model in existing_models.items():
                if model_name not in incoming_model_names:
                    db.delete(model)
            if not has_default:
                first_model = (
                    db.query(ModelItem)
                    .filter(ModelItem.provider_id == target_provider_id, ModelItem.is_enabled.is_(True))
                    .order_by(ModelItem.id.asc())
                    .first()
                )
                if first_model:
                    db.query(ModelItem).filter(ModelItem.provider_id == target_provider_id).update(
                        {ModelItem.is_default: False}, synchronize_session=False
                    )
                    first_model.is_default = True
    return upsert_count


def _ensure_scene_tag(db: Session, name: str) -> SceneTag:
    normalized = name.strip()
    tag = db.query(SceneTag).filter(SceneTag.name == normalized).first()
    if tag:
        return tag
    tag = SceneTag(name=normalized, is_active=True)
    db.add(tag)
    db.flush()
    return tag


def _normalize_seed_package_path(raw_path: str | None) -> str | None:
    if not raw_path:
        return None
    path_value = str(raw_path).strip()
    if not path_value:
        return None
    # Enforce release-local seed package path.
    if path_value.startswith(f"{SEED_SKILL_PACKAGE_ROOT}/"):
        return path_value
    package_name = Path(path_value).name
    if not package_name:
        return None
    return f"{SEED_SKILL_PACKAGE_ROOT}/{package_name}"


def _resolve_seed_skill_icon_path(skill_name: str) -> str | None:
    icon_filename = SKILL_ICON_FILENAME_BY_NAME.get(skill_name.strip().lower())
    if not icon_filename:
        return None
    source_icon = SEED_ICON_DIR / icon_filename
    if not source_icon.exists():
        return None

    settings = get_settings()
    target_dir = Path(settings.UPLOAD_DIR).resolve() / "icons"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_icon = target_dir / icon_filename
    if not target_icon.exists():
        shutil.copy2(source_icon, target_icon)
    return str(target_icon)


def _upsert_skills(
    db: Session,
    owner_id: int,
    source_provider_id_map: dict[int, int],
    skills: list[dict[str, Any]],
) -> int:
    upsert_count = 0

    for item in skills:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        resolved_icon_path = _resolve_seed_skill_icon_path(name)
        target_icon_path = item.get("icon_path") or resolved_icon_path

        skill = db.query(Skill).filter(Skill.name == name).first()
        if not skill:
            skill = Skill(
                name=name,
                description=item.get("description"),
                icon_path=target_icon_path,
                icon_emoji=item.get("icon_emoji"),
                status=str(item.get("status") or "published"),
                sort_weight=int(item.get("sort_weight") or 0),
                use_count=int(item.get("use_count") or 0),
                creator_id=owner_id,
            )
            db.add(skill)
            db.flush()
        else:
            skill.description = item.get("description")
            skill.icon_path = target_icon_path
            skill.icon_emoji = item.get("icon_emoji")
            skill.status = str(item.get("status") or skill.status)
            skill.sort_weight = int(item.get("sort_weight") or skill.sort_weight)
            skill.use_count = int(item.get("use_count") or skill.use_count)

        tag_names = [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()]
        if tag_names:
            tag_entities = [_ensure_scene_tag(db, tag_name) for tag_name in tag_names]
            skill.tags = tag_entities

        version_payload = item.get("version") or {}
        version_number = int(version_payload.get("version_number") or 1)
        source_provider_id = int(version_payload.get("model_provider_id") or 0)
        target_provider_id = source_provider_id_map.get(source_provider_id)
        if not target_provider_id:
            raise RuntimeError(f"missing mapped provider for source model_provider_id={source_provider_id}")

        version = (
            db.query(SkillVersion)
            .filter(
                SkillVersion.skill_id == skill.id,
                SkillVersion.version_number == version_number,
            )
            .first()
        )
        if not version:
            version = SkillVersion(
                skill_id=skill.id,
                version_number=version_number,
                brief_desc=str(version_payload.get("brief_desc") or ""),
                detail_desc=str(version_payload.get("detail_desc") or ""),
                system_prompt=str(version_payload.get("system_prompt") or ""),
                welcome_message=str(version_payload.get("welcome_message") or ""),
                model_provider_id=target_provider_id,
                model_name=str(version_payload.get("model_name") or ""),
                usage_example=version_payload.get("usage_example"),
                package_path=_normalize_seed_package_path(version_payload.get("package_path")),
                change_log=version_payload.get("change_log"),
                mcp_load_mode=str(version_payload.get("mcp_load_mode") or "all"),
            )
            db.add(version)
            db.flush()
        else:
            version.brief_desc = str(version_payload.get("brief_desc") or version.brief_desc)
            version.detail_desc = str(version_payload.get("detail_desc") or version.detail_desc)
            version.system_prompt = str(version_payload.get("system_prompt") or version.system_prompt)
            version.welcome_message = str(version_payload.get("welcome_message") or version.welcome_message)
            version.model_provider_id = target_provider_id
            version.model_name = str(version_payload.get("model_name") or version.model_name)
            version.usage_example = version_payload.get("usage_example")
            version.package_path = _normalize_seed_package_path(version_payload.get("package_path"))
            version.change_log = version_payload.get("change_log")
            version.mcp_load_mode = str(version_payload.get("mcp_load_mode") or version.mcp_load_mode)

        if skill.status == "published":
            skill.published_version_id = version.id
            skill.draft_version_id = version.id
        elif skill.status == "draft":
            skill.draft_version_id = version.id

        upsert_count += 1

    return upsert_count


def _upsert_mcps(db: Session, owner_id: int, mcps: list[dict[str, Any]]) -> int:
    upsert_count = 0

    for item in mcps:
        name = str(item.get("name") or "").strip()
        if not name:
            continue

        config_json = _sanitize_sensitive_values(item.get("config_json") or {})
        transport_type = str(item.get("transport_type") or "").strip() or MCPClientManager.detect_transport_type(config_json)
        encrypted_config = encrypt_mcp_config(config_json)

        mcp = db.query(Mcp).filter(Mcp.name == name).first()
        if not mcp:
            mcp = Mcp(
                name=name,
                description=str(item.get("description") or ""),
                config_json_encrypted=encrypted_config,
                transport_type=transport_type,
                is_enabled=bool(item.get("is_enabled", True)),
                timeout_seconds=int(item.get("timeout_seconds") or 30),
                max_retries=int(item.get("max_retries") or 0),
                circuit_breaker_threshold=int(item.get("circuit_breaker_threshold") or 5),
                circuit_breaker_recovery=int(item.get("circuit_breaker_recovery") or 300),
                access_role=str(item.get("access_role") or "all"),
                creator_id=owner_id,
            )
            db.add(mcp)
            db.flush()
        else:
            mcp.description = str(item.get("description") or mcp.description)
            mcp.config_json_encrypted = encrypted_config
            mcp.transport_type = transport_type
            mcp.is_enabled = bool(item.get("is_enabled", mcp.is_enabled))
            mcp.timeout_seconds = int(item.get("timeout_seconds") or mcp.timeout_seconds)
            mcp.max_retries = int(item.get("max_retries") or mcp.max_retries)
            mcp.circuit_breaker_threshold = int(
                item.get("circuit_breaker_threshold") or mcp.circuit_breaker_threshold
            )
            mcp.circuit_breaker_recovery = int(
                item.get("circuit_breaker_recovery") or mcp.circuit_breaker_recovery
            )
            mcp.access_role = str(item.get("access_role") or mcp.access_role)

        existing_tools = {tool.tool_name: tool for tool in db.query(McpTool).filter(McpTool.mcp_id == mcp.id).all()}
        incoming_names = set()
        for tool_item in item.get("tools") or []:
            tool_name = str(tool_item.get("tool_name") or "").strip()
            if not tool_name:
                continue
            incoming_names.add(tool_name)
            existing = existing_tools.get(tool_name)
            if existing:
                existing.tool_description = tool_item.get("tool_description")
                existing.input_schema = tool_item.get("input_schema")
                existing.is_enabled = True
            else:
                db.add(
                    McpTool(
                        mcp_id=mcp.id,
                        tool_name=tool_name,
                        tool_description=tool_item.get("tool_description"),
                        input_schema=tool_item.get("input_schema"),
                        is_enabled=True,
                    )
                )
        for tool_name, existing in existing_tools.items():
            if tool_name not in incoming_names:
                db.delete(existing)

        upsert_count += 1

    return upsert_count


def _upsert_prompt_templates(db: Session, owner_id: int, templates: list[dict[str, Any]]) -> int:
    upsert_count = 0
    target_global_default_ids: list[int] = []

    for item in templates:
        name = str(item.get("name") or "").strip()
        category = str(item.get("category") or "role").strip() or "role"
        if not name:
            continue

        template = (
            db.query(SystemPromptTemplate)
            .filter(
                SystemPromptTemplate.name == name,
                SystemPromptTemplate.category == category,
                SystemPromptTemplate.visibility == "public",
            )
            .first()
        )
        if not template:
            template = SystemPromptTemplate(
                name=name,
                category=category,
                content=str(item.get("content") or ""),
                is_default=bool(item.get("is_default", False)),
                priority=int(item.get("priority") or 50),
                is_builtin=bool(item.get("is_builtin", False)),
                visibility="public",
                is_global_default=bool(item.get("is_global_default", False)),
                created_by=owner_id,
            )
            db.add(template)
            db.flush()
        else:
            template.content = str(item.get("content") or template.content)
            template.is_default = bool(item.get("is_default", template.is_default))
            template.priority = int(item.get("priority") or template.priority)
            template.is_builtin = bool(item.get("is_builtin", template.is_builtin))
            template.visibility = "public"
            template.is_global_default = bool(item.get("is_global_default", template.is_global_default))
            if not template.created_by:
                template.created_by = owner_id

        if template.is_global_default:
            target_global_default_ids.append(template.id)
        upsert_count += 1

    if target_global_default_ids:
        db.query(SystemPromptTemplate).filter(SystemPromptTemplate.is_global_default.is_(True)).update(
            {"is_global_default": False}
        )
        db.query(SystemPromptTemplate).filter(SystemPromptTemplate.id.in_(target_global_default_ids)).update(
            {"is_global_default": True},
            synchronize_session=False,
        )

    return upsert_count


def _upsert_workflows(
    db: Session,
    owner_id: int,
    workflows: list[dict[str, Any]],
) -> tuple[int, dict[str, int]]:
    upsert_count = 0
    workflow_scope_map: dict[str, int] = {}

    for item in workflows:
        code = str(item.get("code") or "").strip()
        scope = str(item.get("scope") or "").strip().upper()
        if not code or scope not in {"PROJECT", "REQUIREMENT"}:
            continue

        workflow = (
            db.query(WorkflowDefinition)
            .filter(
                WorkflowDefinition.scope == scope,
                WorkflowDefinition.code == code,
            )
            .first()
        )
        if not workflow:
            workflow = WorkflowDefinition(
                name=str(item.get("name") or code),
                code=code,
                scope=scope,
                description=item.get("description"),
                status=str(item.get("status") or "ACTIVE"),
                created_by=owner_id,
                updated_by=owner_id,
            )
            db.add(workflow)
            db.flush()
        else:
            workflow.name = str(item.get("name") or workflow.name)
            workflow.description = item.get("description")
            workflow.status = str(item.get("status") or workflow.status)
            workflow.updated_by = owner_id

        version_payload = item.get("version") or {}
        version = (
            db.query(WorkflowDefinitionVersion)
            .filter(
                WorkflowDefinitionVersion.workflow_definition_id == workflow.id,
                WorkflowDefinitionVersion.version_no == 1,
            )
            .first()
        )
        if not version:
            version = WorkflowDefinitionVersion(
                workflow_definition_id=workflow.id,
                version_no=1,
                version_label=str(version_payload.get("version_label") or "V1"),
                is_published=True,
                published_by=owner_id,
                schema_json=_normalize_json_value(version_payload.get("schema_json")) or {},
            )
            db.add(version)
            db.flush()
        else:
            version.version_label = str(version_payload.get("version_label") or version.version_label or "V1")
            version.is_published = True
            version.published_by = owner_id
            version.schema_json = _normalize_json_value(version_payload.get("schema_json")) or version.schema_json or {}

        # Ensure only V1 stays published for this seed workflow.
        db.query(WorkflowDefinitionVersion).filter(
            WorkflowDefinitionVersion.workflow_definition_id == workflow.id,
            WorkflowDefinitionVersion.id != version.id,
        ).update({"is_published": False}, synchronize_session=False)

        existing_nodes = {
            node.node_code: node
            for node in db.query(WorkflowDefinitionNode).filter(
                WorkflowDefinitionNode.workflow_definition_version_id == version.id
            ).all()
        }
        incoming_node_codes: set[str] = set()
        for node_payload in version_payload.get("nodes") or []:
            node_code = str(node_payload.get("node_code") or "").strip()
            if not node_code:
                continue
            incoming_node_codes.add(node_code)
            skill_name = str(node_payload.get("skill_name") or "").strip()
            skill = db.query(Skill).filter(Skill.name == skill_name).first() if skill_name else None
            skill_id = skill.id if skill else None

            existing_node = existing_nodes.get(node_code)
            if existing_node:
                existing_node.node_name = str(node_payload.get("node_name") or existing_node.node_name)
                existing_node.node_order = int(node_payload.get("node_order") or existing_node.node_order)
                existing_node.skill_id = skill_id
                existing_node.input_mapping_json = _normalize_json_value(node_payload.get("input_mapping_json"))
                existing_node.output_type = node_payload.get("output_type")
                existing_node.retry_policy_json = _normalize_json_value(node_payload.get("retry_policy_json"))
            else:
                db.add(
                    WorkflowDefinitionNode(
                        workflow_definition_version_id=version.id,
                        node_code=node_code,
                        node_name=str(node_payload.get("node_name") or node_code),
                        node_order=int(node_payload.get("node_order") or 1),
                        skill_id=skill_id,
                        input_mapping_json=_normalize_json_value(node_payload.get("input_mapping_json")),
                        output_type=node_payload.get("output_type"),
                        retry_policy_json=_normalize_json_value(node_payload.get("retry_policy_json")),
                    )
                )

        for node_code, node in existing_nodes.items():
            if node_code not in incoming_node_codes:
                db.delete(node)

        workflow_scope_map[scope] = workflow.id
        upsert_count += 1

    return upsert_count, workflow_scope_map


def _ensure_sample_workflow_instance(
    db: Session,
    owner_id: int,
    requirement: Requirement,
    workflow_definition_id: int,
) -> tuple[WorkflowInstance | None, WorkflowInstanceNode | None]:
    published_version = (
        db.query(WorkflowDefinitionVersion)
        .filter(
            WorkflowDefinitionVersion.workflow_definition_id == workflow_definition_id,
            WorkflowDefinitionVersion.is_published.is_(True),
        )
        .order_by(WorkflowDefinitionVersion.version_no.desc(), WorkflowDefinitionVersion.id.desc())
        .first()
    )
    if not published_version:
        return None, None

    instance = None
    if requirement.workflow_instance_id:
        instance = db.query(WorkflowInstance).filter(WorkflowInstance.id == requirement.workflow_instance_id).first()

    if not instance:
        instance = (
            db.query(WorkflowInstance)
            .filter(
                WorkflowInstance.scope_type == "REQUIREMENT",
                WorkflowInstance.scope_id == requirement.id,
            )
            .order_by(WorkflowInstance.id.asc())
            .first()
        )

    if not instance:
        instance = WorkflowInstance(
            scope_type="REQUIREMENT",
            scope_id=requirement.id,
            workflow_definition_id=workflow_definition_id,
            workflow_definition_version_id=published_version.id,
            status="NOT_STARTED",
            created_by=owner_id,
            updated_by=owner_id,
        )
        db.add(instance)
        db.flush()

    definition_nodes = (
        db.query(WorkflowDefinitionNode)
        .filter(WorkflowDefinitionNode.workflow_definition_version_id == published_version.id)
        .order_by(WorkflowDefinitionNode.node_order.asc())
        .all()
    )
    if not definition_nodes:
        return instance, None

    existing_nodes = {
        node.node_code: node
        for node in db.query(WorkflowInstanceNode).filter(
            WorkflowInstanceNode.workflow_instance_id == instance.id
        ).all()
    }
    first_node: WorkflowInstanceNode | None = None
    for definition_node in definition_nodes:
        node = existing_nodes.get(definition_node.node_code)
        if not node:
            node = WorkflowInstanceNode(
                workflow_instance_id=instance.id,
                definition_node_id=definition_node.id,
                node_code=definition_node.node_code,
                node_name=definition_node.node_name,
                node_order=definition_node.node_order,
                status="PENDING",
                updated_by=owner_id,
            )
            db.add(node)
            db.flush()
        if first_node is None:
            first_node = node

    if first_node:
        instance.current_node_id = first_node.id
    requirement.workflow_instance_id = instance.id
    requirement.workflow_definition_id = workflow_definition_id
    requirement.updated_by = owner_id

    return instance, first_node


def _ensure_sample_project_requirement_conversation(
    db: Session,
    owner_id: int,
    workflow_scope_map: dict[str, int],
) -> dict[str, int]:
    sample_project_name = "示例项目（开源演示）"
    sample_requirement_titles = [
        "示例需求 1：统一需求收集入口",
        "示例需求 2：需求评审流程透明化",
        "示例需求 3：需求变更追踪与回溯",
    ]
    sample_conversation_title = "示例对话：需求澄清与拆解"

    owner_user = db.query(User).filter(User.id == owner_id).first()
    project = db.query(Project).filter(Project.name == sample_project_name).first()
    if not project:
        project = Project(
            name=sample_project_name,
            level="P1",
            workflow_definition_id=workflow_scope_map.get("PROJECT"),
            created_by=owner_id,
            updated_by=owner_id,
        )
        db.add(project)
        db.flush()
    else:
        project.workflow_definition_id = workflow_scope_map.get("PROJECT")
        project.updated_by = owner_id

    if owner_user and owner_user not in (project.owners or []):
        project.owners.append(owner_user)

    requirements: list[Requirement] = []
    for idx, title in enumerate(sample_requirement_titles, start=1):
        requirement = (
            db.query(Requirement)
            .filter(
                Requirement.project_id == project.id,
                Requirement.title == title,
            )
            .first()
        )
        if not requirement:
            requirement = Requirement(
                project_id=project.id,
                title=title,
                priority="P1" if idx == 1 else "P2",
                status="NOT_STARTED",
                description="这是开源版初始化生成的示例需求，可按需修改或删除。",
                workflow_definition_id=workflow_scope_map.get("REQUIREMENT"),
                created_by=owner_id,
                updated_by=owner_id,
            )
            db.add(requirement)
            db.flush()
        else:
            requirement.workflow_definition_id = workflow_scope_map.get("REQUIREMENT")
            requirement.updated_by = owner_id
        requirements.append(requirement)

    # Bind one sample conversation to the first requirement through workflow node binding.
    target_requirement = requirements[0] if requirements else None
    first_node = None
    if target_requirement and workflow_scope_map.get("REQUIREMENT"):
        _instance, first_node = _ensure_sample_workflow_instance(
            db=db,
            owner_id=owner_id,
            requirement=target_requirement,
            workflow_definition_id=workflow_scope_map["REQUIREMENT"],
        )

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == owner_id,
            Conversation.title == sample_conversation_title,
        )
        .first()
    )
    if not conversation:
        conversation = Conversation(
            user_id=owner_id,
            title=sample_conversation_title,
            is_test=False,
        )
        db.add(conversation)
        db.flush()

    existing_messages = db.query(Message).filter(Message.conversation_id == conversation.id).count()
    if existing_messages == 0:
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content="请帮我梳理这个需求的目标、范围和验收标准。",
            )
        )
        db.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="已为你生成需求澄清建议：目标、范围、里程碑、验收标准与风险清单。",
            )
        )

    if first_node:
        binding = (
            db.query(WorkflowNodeConversation)
            .filter(WorkflowNodeConversation.conversation_id == conversation.id)
            .first()
        )
        if not binding:
            db.add(
                WorkflowNodeConversation(
                    workflow_instance_node_id=first_node.id,
                    conversation_id=conversation.id,
                    binding_type="MANUAL",
                    created_by=owner_id,
                )
            )

    return {
        "project_id": project.id,
        "requirement_count": len(requirements),
        "conversation_id": conversation.id,
    }


def init_release_seed() -> None:
    db: Session = SessionLocal()
    try:
        owner_id = _get_seed_owner_id(db)

        providers = _load_seed_file("model_providers.json")
        skills = _load_seed_file("skills.json")
        mcps = _load_seed_file("mcps.json")
        templates = _load_seed_file("prompt_templates.json")
        workflows = _load_seed_file("workflows.json")
        model_items_seed = _load_seed_file("model_items.json")

        source_provider_id_map, provider_count = _upsert_model_providers(db, owner_id, providers)
        model_count = _upsert_model_items(db, source_provider_id_map, model_items_seed)
        skill_count = _upsert_skills(db, owner_id, source_provider_id_map, skills)
        mcp_count = _upsert_mcps(db, owner_id, mcps)
        template_count = _upsert_prompt_templates(db, owner_id, templates)
        workflow_count, workflow_scope_map = _upsert_workflows(db, owner_id, workflows)
        sample_seed_result = _ensure_sample_project_requirement_conversation(db, owner_id, workflow_scope_map)

        db.commit()
        print(
            "release seed completed: "
            f"providers={provider_count}, models={model_count}, skills={skill_count}, mcps={mcp_count}, "
            f"prompt_templates={template_count}, workflows={workflow_count}, "
            f"sample_project_id={sample_seed_result['project_id']}, "
            f"sample_requirements={sample_seed_result['requirement_count']}, "
            f"sample_conversation_id={sample_seed_result['conversation_id']}"
        )
    except Exception as exc:
        db.rollback()
        print(f"release seed failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_release_seed()
