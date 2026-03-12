import asyncio
import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.models.conversation import Conversation
from app.models.project import Project
from app.models.reference import ConversationReferenceState
from app.models.requirement import Requirement
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionNode,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowInstanceNode,
    WorkflowNodeConversation,
)
from app.services.reference_service import (
    SANDBOX_FILE_ID_OFFSET,
    assemble_reference_context,
    ensure_reference_state,
    get_conversation_binding_context,
    get_or_build_catalog,
    resolve_scope_snapshot_for_state,
)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_workflow_instance(db: Session, user: User, requirement: Requirement) -> tuple[WorkflowInstanceNode, WorkflowInstanceNode]:
    definition = WorkflowDefinition(
        name="Reference Scope Flow",
        code="REF_SCOPE_FLOW",
        scope="REQUIREMENT",
        status="ACTIVE",
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(definition)
    db.flush()

    version = WorkflowDefinitionVersion(
        workflow_definition_id=definition.id,
        version_no=1,
        version_label="initial",
        is_published=True,
        published_at=datetime.now(),
        published_by=user.id,
        schema_json={"nodes": ["N1", "N2"]},
    )
    db.add(version)
    db.flush()

    def_node_1 = WorkflowDefinitionNode(
        workflow_definition_version_id=version.id,
        node_code="N1",
        node_name="N1",
        node_order=1,
        skill_id=None,
    )
    def_node_2 = WorkflowDefinitionNode(
        workflow_definition_version_id=version.id,
        node_code="N2",
        node_name="N2",
        node_order=2,
        skill_id=None,
    )
    db.add_all([def_node_1, def_node_2])
    db.flush()

    instance = WorkflowInstance(
        scope_type="REQUIREMENT",
        scope_id=requirement.id,
        workflow_definition_id=definition.id,
        workflow_definition_version_id=version.id,
        status="IN_PROGRESS",
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(instance)
    db.flush()

    node_1 = WorkflowInstanceNode(
        workflow_instance_id=instance.id,
        definition_node_id=def_node_1.id,
        node_code="N1",
        node_name="N1",
        node_order=1,
        status="PENDING",
        updated_by=user.id,
    )
    node_2 = WorkflowInstanceNode(
        workflow_instance_id=instance.id,
        definition_node_id=def_node_2.id,
        node_code="N2",
        node_name="N2",
        node_order=2,
        status="PENDING",
        updated_by=user.id,
    )
    db.add_all([node_1, node_2])
    db.flush()
    instance.current_node_id = node_1.id
    db.flush()
    return node_1, node_2


def test_catalog_includes_bound_conversation_sandbox_files(db_session: Session):
    user = User(username="ref_user", password_hash="pwd", display_name="Ref User", role="user")
    db_session.add(user)
    db_session.flush()

    project = Project(name="P1", level="P1", created_by=user.id, updated_by=user.id)
    db_session.add(project)
    db_session.flush()

    requirement = Requirement(
        project_id=project.id,
        title="需求 A",
        priority="P1",
        created_by=user.id,
        updated_by=user.id,
    )
    db_session.add(requirement)
    db_session.flush()

    node_1, node_2 = _seed_workflow_instance(db_session, user, requirement)

    conv_500 = Conversation(user_id=user.id, title="chat/500")
    conv_497 = Conversation(user_id=user.id, title="chat/497")
    db_session.add_all([conv_500, conv_497])
    db_session.flush()

    db_session.add_all(
        [
            WorkflowNodeConversation(
                workflow_instance_node_id=node_1.id,
                conversation_id=conv_500.id,
                binding_type="AUTO",
                created_by=user.id,
            ),
            WorkflowNodeConversation(
                workflow_instance_node_id=node_2.id,
                conversation_id=conv_497.id,
                binding_type="AUTO",
                created_by=user.id,
            ),
        ]
    )
    db_session.flush()

    sandbox_file = UploadedFile(
        conversation_id=conv_497.id,
        user_id=user.id,
        original_name="需求变更说明.md",
        stored_path="uploads/sandbox/test.md",
        file_size=128,
        file_type="md",
        extracted_text="这是来自 chat/497 的需求变更摘要。",
        source="generated",
        sandbox_path="generated/需求变更说明.md",
    )
    db_session.add(sandbox_file)
    db_session.flush()

    _, catalog = get_or_build_catalog(conv_500, db_session, force_rebuild=True)
    sandbox_entries = [item for item in catalog if item.get("source_kind") == "SANDBOX_FILE"]
    assert sandbox_entries, "应包含同流程实例其他节点绑定会话的沙箱文件"

    target = next((item for item in sandbox_entries if item.get("conversation_id") == conv_497.id), None)
    assert target is not None
    assert target["file_id"] == SANDBOX_FILE_ID_OFFSET + sandbox_file.id

    state = (
        db_session.query(ConversationReferenceState)
        .filter(ConversationReferenceState.conversation_id == conv_500.id)
        .first()
    )
    assert state is not None
    state.selected_file_ids = [target["file_id"]]
    db_session.flush()

    assembled = asyncio.run(assemble_reference_context(db_session, conv_500.id, query_text="需求变更"))
    assert target["file_id"] in assembled.selected_file_ids
    assert assembled.content and "chat/497" in assembled.content
    assert "需求变更摘要" in assembled.content


def test_catalog_rebuilds_for_workflow_bound_conversation(db_session: Session):
    user = User(username="ref_user2", password_hash="pwd", display_name="Ref User2", role="user")
    db_session.add(user)
    db_session.flush()

    project = Project(name="P2", level="P1", created_by=user.id, updated_by=user.id)
    db_session.add(project)
    db_session.flush()

    requirement = Requirement(
        project_id=project.id,
        title="需求 B",
        priority="P1",
        created_by=user.id,
        updated_by=user.id,
    )
    db_session.add(requirement)
    db_session.flush()

    node_1, node_2 = _seed_workflow_instance(db_session, user, requirement)
    conv_500 = Conversation(user_id=user.id, title="chat/500")
    conv_497 = Conversation(user_id=user.id, title="chat/497")
    db_session.add_all([conv_500, conv_497])
    db_session.flush()

    db_session.add(
        WorkflowNodeConversation(
            workflow_instance_node_id=node_1.id,
            conversation_id=conv_500.id,
            binding_type="AUTO",
            created_by=user.id,
        )
    )
    db_session.flush()

    snapshot_id_1, catalog_1 = get_or_build_catalog(conv_500, db_session, force_rebuild=False)
    assert snapshot_id_1 > 0
    assert not any(item.get("source_kind") == "SANDBOX_FILE" for item in catalog_1)

    db_session.add(
        WorkflowNodeConversation(
            workflow_instance_node_id=node_2.id,
            conversation_id=conv_497.id,
            binding_type="AUTO",
            created_by=user.id,
        )
    )
    db_session.add(
        UploadedFile(
            conversation_id=conv_497.id,
            user_id=user.id,
            original_name="跨节点资料.md",
            stored_path="uploads/sandbox/test2.md",
            file_size=96,
            file_type="md",
            extracted_text="后续新增的跨节点资料",
            source="generated",
            sandbox_path="generated/跨节点资料.md",
        )
    )
    db_session.flush()

    snapshot_id_2, catalog_2 = get_or_build_catalog(conv_500, db_session, force_rebuild=False)
    assert snapshot_id_2 != snapshot_id_1, "工作流绑定对话应触发范围重建，避免使用陈旧快照"
    assert any(item.get("source_kind") == "SANDBOX_FILE" for item in catalog_2)


def test_resolve_scope_snapshot_returns_none_when_conversation_unbound(db_session: Session):
    user = User(username="ref_user3", password_hash="pwd", display_name="Ref User3", role="user")
    db_session.add(user)
    db_session.flush()

    conv = Conversation(user_id=user.id, title="chat/unbound")
    db_session.add(conv)
    db_session.flush()

    state = ensure_reference_state(db_session, conv.id, user.id)
    state.scope_snapshot_id = 999
    db_session.flush()

    effective_snapshot_id = resolve_scope_snapshot_for_state(db_session, conv, state)
    assert effective_snapshot_id is None


def test_resolve_scope_snapshot_builds_when_conversation_bound(db_session: Session):
    user = User(username="ref_user4", password_hash="pwd", display_name="Ref User4", role="user")
    db_session.add(user)
    db_session.flush()

    project = Project(name="P4", level="P1", created_by=user.id, updated_by=user.id)
    db_session.add(project)
    db_session.flush()

    requirement = Requirement(
        project_id=project.id,
        title="需求 D",
        priority="P1",
        created_by=user.id,
        updated_by=user.id,
    )
    db_session.add(requirement)
    db_session.flush()

    node_1, _ = _seed_workflow_instance(db_session, user, requirement)
    conv = Conversation(user_id=user.id, title="chat/bound")
    db_session.add(conv)
    db_session.flush()

    db_session.add(
        WorkflowNodeConversation(
            workflow_instance_node_id=node_1.id,
            conversation_id=conv.id,
            binding_type="AUTO",
            created_by=user.id,
        )
    )
    db_session.flush()

    state = ensure_reference_state(db_session, conv.id, user.id)
    assert state.scope_snapshot_id is None

    effective_snapshot_id = resolve_scope_snapshot_for_state(db_session, conv, state)
    assert isinstance(effective_snapshot_id, int)
    assert effective_snapshot_id > 0


def test_get_conversation_binding_context_for_requirement(db_session: Session):
    user = User(username="ref_user5", password_hash="pwd", display_name="Ref User5", role="user")
    db_session.add(user)
    db_session.flush()

    project = Project(name="项目 A", level="P1", created_by=user.id, updated_by=user.id)
    db_session.add(project)
    db_session.flush()

    requirement = Requirement(
        project_id=project.id,
        title="需求 X",
        priority="P1",
        created_by=user.id,
        updated_by=user.id,
    )
    db_session.add(requirement)
    db_session.flush()

    node_1, _ = _seed_workflow_instance(db_session, user, requirement)
    conv = Conversation(user_id=user.id, title="chat/bind-detail")
    db_session.add(conv)
    db_session.flush()

    db_session.add(
        WorkflowNodeConversation(
            workflow_instance_node_id=node_1.id,
            conversation_id=conv.id,
            binding_type="AUTO",
            created_by=user.id,
        )
    )
    db_session.flush()

    context = get_conversation_binding_context(db_session, conv.id)
    assert context["is_bound"] is True
    assert context["scope_type"] == "REQUIREMENT"
    assert context["scope_title"] == "需求 X"
    assert context["node_name"] == "N1"


def test_get_conversation_binding_context_for_unbound_conversation(db_session: Session):
    user = User(username="ref_user6", password_hash="pwd", display_name="Ref User6", role="user")
    db_session.add(user)
    db_session.flush()

    conv = Conversation(user_id=user.id, title="chat/unbound-detail")
    db_session.add(conv)
    db_session.flush()

    context = get_conversation_binding_context(db_session, conv.id)
    assert context["is_bound"] is False
