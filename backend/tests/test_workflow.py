from datetime import datetime
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.models.conversation import Conversation
from app.models.skill import Skill
from app.models.user import User
from app.models.workflow import (
    WorkflowDefinition,
    WorkflowDefinitionNode,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowInstanceNode,
    WorkflowNodeConversation,
    WorkflowInstanceNodeOutput,
    WorkflowTransitionLog,
)
from app.routers.admin_workflows import create_workflow_version, delete_draft_version
from app.schemas.workflow_delivery import WorkflowVersionCreate
from app.services.workflow_instance_service import (
    create_workflow_instance,
    mark_node_running_on_conversation_bind,
)
from app.services.workflow_version_service import switch_instances_to_version


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


def _seed_user_and_skill(db: Session) -> tuple[User, Skill]:
    user = User(
        username="v83_user",
        password_hash="pwd",
        display_name="Workflow User",
        role="admin",
    )
    db.add(user)
    db.flush()

    skill = Skill(
        name="NodeSkill",
        description="for workflow node",
        status="published",
        sort_weight=0,
        use_count=0,
        creator_id=user.id,
    )
    db.add(skill)
    db.flush()
    return user, skill


def _seed_definition_with_version(
    db: Session,
    user_id: int,
    skill_id: int,
    version_no: int,
    nodes: list[tuple[str, int]],
    published: bool = True,
) -> tuple[WorkflowDefinition, WorkflowDefinitionVersion]:
    definition = (
        db.query(WorkflowDefinition)
        .filter(WorkflowDefinition.code == "REQ_FLOW", WorkflowDefinition.scope == "REQUIREMENT")
        .first()
    )
    if not definition:
        definition = WorkflowDefinition(
            name="Requirement Flow",
            code="REQ_FLOW",
            scope="REQUIREMENT",
            status="ACTIVE",
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(definition)
        db.flush()

    version = WorkflowDefinitionVersion(
        workflow_definition_id=definition.id,
        version_no=version_no,
        version_label=f"v{version_no}",
        is_published=published,
        published_at=datetime.now() if published else None,
        published_by=user_id if published else None,
        schema_json={"nodes": [code for code, _ in nodes]},
    )
    db.add(version)
    db.flush()

    for code, order in nodes:
        db.add(
            WorkflowDefinitionNode(
                workflow_definition_version_id=version.id,
                node_code=code,
                node_name=code,
                node_order=order,
                skill_id=skill_id,
            )
        )

    db.flush()
    return definition, version


def test_create_workflow_instance_initializes_pending_nodes(db_session: Session):
    user, skill = _seed_user_and_skill(db_session)
    definition, version = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=1,
        nodes=[("N1", 1), ("N2", 2), ("N3", 3)],
        published=True,
    )

    instance = create_workflow_instance(
        db=db_session,
        scope_type="REQUIREMENT",
        scope_id=1001,
        workflow_definition_id=definition.id,
        operator_id=user.id,
    )
    db_session.commit()

    persisted = db_session.query(WorkflowInstance).filter(WorkflowInstance.id == instance.id).first()
    assert persisted is not None
    assert persisted.workflow_definition_version_id == version.id
    assert persisted.status == "IN_PROGRESS"

    nodes = (
        db_session.query(WorkflowInstanceNode)
        .filter(WorkflowInstanceNode.workflow_instance_id == instance.id)
        .order_by(WorkflowInstanceNode.node_order.asc())
        .all()
    )
    assert [node.status for node in nodes] == ["PENDING", "PENDING", "PENDING"]
    assert persisted.current_node_id == nodes[0].id


def test_publish_switches_instances_to_new_version(db_session: Session):
    user, skill = _seed_user_and_skill(db_session)
    definition, version_v1 = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=1,
        nodes=[("N1", 1), ("N2", 2)],
        published=True,
    )
    version_v2_nodes = [("N1", 1), ("N2", 2), ("N3", 3)]
    _, version_v2 = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=2,
        nodes=version_v2_nodes,
        published=False,
    )

    instance = create_workflow_instance(
        db=db_session,
        scope_type="REQUIREMENT",
        scope_id=2002,
        workflow_definition_id=definition.id,
        operator_id=user.id,
    )
    running_node = (
        db_session.query(WorkflowInstanceNode)
        .filter(
            WorkflowInstanceNode.workflow_instance_id == instance.id,
            WorkflowInstanceNode.node_code == "N1",
        )
        .first()
    )
    assert running_node is not None
    running_node.status = "RUNNING"
    db_session.flush()

    switched = switch_instances_to_version(
        db=db_session,
        workflow_definition_id=definition.id,
        target_version_id=version_v2.id,
        operator_user_id=user.id,
    )
    db_session.commit()

    assert switched == 1
    refreshed = db_session.query(WorkflowInstance).filter(WorkflowInstance.id == instance.id).first()
    assert refreshed is not None
    assert refreshed.workflow_definition_version_id == version_v2.id

    nodes = (
        db_session.query(WorkflowInstanceNode)
        .filter(WorkflowInstanceNode.workflow_instance_id == instance.id)
        .order_by(WorkflowInstanceNode.node_order.asc())
        .all()
    )
    by_code = {node.node_code: node for node in nodes}
    assert by_code["N1"].status == "PENDING"
    assert by_code["N3"].status == "BLOCKED"

    logs = (
        db_session.query(WorkflowTransitionLog)
        .filter(WorkflowTransitionLog.workflow_instance_id == instance.id)
        .all()
    )
    assert any(log.action == "SWITCH_VERSION" for log in logs)


def test_conversation_can_only_bind_one_workflow_node(db_session: Session):
    user, skill = _seed_user_and_skill(db_session)
    definition, _ = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=1,
        nodes=[("N1", 1), ("N2", 2)],
        published=True,
    )
    instance = create_workflow_instance(
        db=db_session,
        scope_type="REQUIREMENT",
        scope_id=3003,
        workflow_definition_id=definition.id,
        operator_id=user.id,
    )

    conv = Conversation(user_id=user.id, title="for bind test")
    db_session.add(conv)
    db_session.flush()

    node_1 = (
        db_session.query(WorkflowInstanceNode)
        .filter(
            WorkflowInstanceNode.workflow_instance_id == instance.id,
            WorkflowInstanceNode.node_code == "N1",
        )
        .first()
    )
    node_2 = (
        db_session.query(WorkflowInstanceNode)
        .filter(
            WorkflowInstanceNode.workflow_instance_id == instance.id,
            WorkflowInstanceNode.node_code == "N2",
        )
        .first()
    )
    assert node_1 is not None
    assert node_2 is not None

    db_session.add(
        WorkflowNodeConversation(
            workflow_instance_node_id=node_1.id,
            conversation_id=conv.id,
            created_by=user.id,
        )
    )
    db_session.commit()

    db_session.add(
        WorkflowNodeConversation(
            workflow_instance_node_id=node_2.id,
            conversation_id=conv.id,
            created_by=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_new_draft_version_blocked_when_latest_version_has_no_nodes(db_session: Session):
    user, _skill = _seed_user_and_skill(db_session)
    definition = WorkflowDefinition(
        name="Draft Guard Flow",
        code="DRAFT_GUARD_FLOW",
        scope="REQUIREMENT",
        status="ACTIVE",
        created_by=user.id,
        updated_by=user.id,
    )
    db_session.add(definition)
    db_session.flush()

    empty_version = WorkflowDefinitionVersion(
        workflow_definition_id=definition.id,
        version_no=1,
        is_published=False,
        schema_json={},
    )
    db_session.add(empty_version)
    db_session.commit()

    res = create_workflow_version(
        definition_id=definition.id,
        body=WorkflowVersionCreate(),
        db=db_session,
        _current_user=user,
    )

    assert res.code == 40001
    assert "没有任何节点" in res.message


def test_create_new_draft_version_clones_source_nodes(db_session: Session):
    user, skill = _seed_user_and_skill(db_session)
    definition, version_v1 = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=1,
        nodes=[("N1", 1), ("N2", 2)],
        published=True,
    )
    db_session.commit()

    res = create_workflow_version(
        definition_id=definition.id,
        body=WorkflowVersionCreate(source_version_id=version_v1.id),
        db=db_session,
        _current_user=user,
    )

    assert res.code == 0
    new_version_id = res.data["id"]
    nodes = (
        db_session.query(WorkflowDefinitionNode)
        .filter(WorkflowDefinitionNode.workflow_definition_version_id == new_version_id)
        .order_by(WorkflowDefinitionNode.node_order.asc())
        .all()
    )
    assert [(node.node_code, node.node_order) for node in nodes] == [("N1", 1), ("N2", 2)]


def test_delete_draft_version_success(db_session: Session):
    user, skill = _seed_user_and_skill(db_session)
    definition, _version_v1 = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=1,
        nodes=[("N1", 1)],
        published=True,
    )
    _definition, version_v2 = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=2,
        nodes=[("N1", 1), ("N2", 2)],
        published=False,
    )
    db_session.commit()

    res = delete_draft_version(
        version_id=version_v2.id,
        db=db_session,
        _current_user=user,
    )
    assert res.code == 0

    left_versions = (
        db_session.query(WorkflowDefinitionVersion)
        .filter(WorkflowDefinitionVersion.workflow_definition_id == definition.id)
        .order_by(WorkflowDefinitionVersion.version_no.asc())
        .all()
    )
    assert [item.version_no for item in left_versions] == [1]


def test_node_output_version_increment_and_current_switch(db_session: Session):
    user, skill = _seed_user_and_skill(db_session)
    definition, _ = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=1,
        nodes=[("N1", 1)],
        published=True,
    )
    instance = create_workflow_instance(
        db=db_session,
        scope_type="REQUIREMENT",
        scope_id=4004,
        workflow_definition_id=definition.id,
        operator_id=user.id,
    )
    node = (
        db_session.query(WorkflowInstanceNode)
        .filter(
            WorkflowInstanceNode.workflow_instance_id == instance.id,
            WorkflowInstanceNode.node_code == "N1",
        )
        .first()
    )
    assert node is not None

    output_v1 = WorkflowInstanceNodeOutput(
        workflow_instance_node_id=node.id,
        output_kind="AGGREGATED",
        deliverable_type="PRD",
        version_no=1,
        content_type="MARKDOWN",
        content_ref="ref_1",
        is_current=False,
        created_by=user.id,
    )
    output_v2 = WorkflowInstanceNodeOutput(
        workflow_instance_node_id=node.id,
        output_kind="AGGREGATED",
        deliverable_type="PRD",
        version_no=2,
        content_type="MARKDOWN",
        content_ref="ref_2",
        is_current=True,
        created_by=user.id,
    )
    db_session.add_all([output_v1, output_v2])
    db_session.commit()

    next_version = (
        db_session.query(WorkflowInstanceNodeOutput.version_no)
        .filter(
            WorkflowInstanceNodeOutput.workflow_instance_node_id == node.id,
            WorkflowInstanceNodeOutput.deliverable_type == "PRD",
        )
        .order_by(WorkflowInstanceNodeOutput.version_no.desc())
        .first()
    )
    assert next_version is not None
    assert next_version[0] == 2

    output_v2.is_current = False
    output_v1.is_current = True
    db_session.commit()

    refreshed = (
        db_session.query(WorkflowInstanceNodeOutput)
        .filter(WorkflowInstanceNodeOutput.workflow_instance_node_id == node.id)
        .order_by(WorkflowInstanceNodeOutput.version_no.asc())
        .all()
    )
    assert refreshed[0].is_current is True
    assert refreshed[1].is_current is False


def test_bind_conversation_promotes_pending_node_to_running(db_session: Session):
    user, skill = _seed_user_and_skill(db_session)
    definition, _ = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=1,
        nodes=[("N1", 1)],
        published=True,
    )
    instance = create_workflow_instance(
        db=db_session,
        scope_type="REQUIREMENT",
        scope_id=5005,
        workflow_definition_id=definition.id,
        operator_id=user.id,
    )
    node = (
        db_session.query(WorkflowInstanceNode)
        .filter(
            WorkflowInstanceNode.workflow_instance_id == instance.id,
            WorkflowInstanceNode.node_code == "N1",
        )
        .first()
    )
    assert node is not None
    assert node.status == "PENDING"
    assert node.started_at is None

    changed = mark_node_running_on_conversation_bind(node, user.id)

    assert changed is True
    assert node.status == "RUNNING"
    assert node.started_at is not None
    assert node.updated_by == user.id


def test_bind_conversation_does_not_override_non_pending_node(db_session: Session):
    user, skill = _seed_user_and_skill(db_session)
    definition, _ = _seed_definition_with_version(
        db_session,
        user.id,
        skill.id,
        version_no=1,
        nodes=[("N1", 1)],
        published=True,
    )
    instance = create_workflow_instance(
        db=db_session,
        scope_type="REQUIREMENT",
        scope_id=6006,
        workflow_definition_id=definition.id,
        operator_id=user.id,
    )
    node = (
        db_session.query(WorkflowInstanceNode)
        .filter(
            WorkflowInstanceNode.workflow_instance_id == instance.id,
            WorkflowInstanceNode.node_code == "N1",
        )
        .first()
    )
    assert node is not None
    node.status = "RUNNING"
    existing_started_at = datetime.now()
    node.started_at = existing_started_at
    db_session.flush()

    changed = mark_node_running_on_conversation_bind(node, user.id)

    assert changed is False
    assert node.status == "RUNNING"
    assert node.started_at == existing_started_at
