from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
import app.models  # noqa: F401
from app.models.conversation import Conversation
from app.models.user import User
from app.services.audit_service import AuditEventCollector, AuditEventWriter, AuditQueryService


def _build_db_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _seed_user_conversation(db):
    user = User(
        username="admin",
        password_hash="hashed",
        display_name="管理员",
        role="admin",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.flush()

    conversation = Conversation(
        user_id=user.id,
        title="test",
        current_provider_id=1,
        current_model_name="deepseek-chat",
        is_test=False,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    db.refresh(user)
    return user, conversation


def test_hash_calculation_is_stable():
    payload = '{"a":1,"b":"ok"}'
    writer = AuditEventWriter(db=None)

    hash_a = writer.compute_payload_sha256(payload)
    hash_b = writer.compute_payload_sha256(payload)

    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_append_only_writes_multiple_events_without_mutation():
    db = _build_db_session()
    user, conversation = _seed_user_conversation(db)

    collector = AuditEventCollector(db)
    ctx = collector.init_trace(conversation.id, user.id, round_no=1)

    collector.append_event(
        ctx,
        event_type="llm_request_raw",
        source="backend",
        payload={"messages": [{"role": "user", "content": "hello"}]},
    )
    collector.append_event(
        ctx,
        event_type="llm_response_raw",
        source="llm",
        payload={"type": "content_delta", "content": "world"},
    )
    db.commit()

    service = AuditQueryService(db)
    replay = service.get_replay(ctx.trace_id)

    assert len(replay["events"]) == 2
    assert replay["events"][0]["id"] != replay["events"][1]["id"]


def test_trace_abnormal_marking_on_failure_events():
    db = _build_db_session()
    user, conversation = _seed_user_conversation(db)

    collector = AuditEventCollector(db)
    ctx = collector.init_trace(conversation.id, user.id, round_no=1)
    collector.append_event(
        ctx,
        event_type="tool_call_failed",
        source="mcp",
        payload={"tool": "search"},
        error_message="tool timeout",
    )
    db.commit()

    timeline = AuditQueryService(db).get_timeline(conversation.id)

    assert timeline["rounds"][0]["is_abnormal"] is True
    assert "tool_call_failed" in timeline["rounds"][0]["abnormal_types"]


def test_replay_returns_events_sorted_by_event_time():
    db = _build_db_session()
    user, conversation = _seed_user_conversation(db)

    collector = AuditEventCollector(db)
    ctx = collector.init_trace(conversation.id, user.id, round_no=2)

    writer = AuditEventWriter(db)
    now = datetime.now()
    writer.append_event(
        trace_id=ctx.trace_id,
        conversation_id=conversation.id,
        message_id=None,
        round_no=2,
        event_type="llm_response_raw",
        source="llm",
        payload_raw='{"idx":2}',
        event_time=now + timedelta(seconds=2),
    )
    writer.append_event(
        trace_id=ctx.trace_id,
        conversation_id=conversation.id,
        message_id=None,
        round_no=2,
        event_type="llm_request_raw",
        source="backend",
        payload_raw='{"idx":1}',
        event_time=now,
    )
    db.commit()

    replay = AuditQueryService(db).get_replay(ctx.trace_id)

    assert len(replay["events"]) == 2
    assert replay["events"][0]["event_type"] == "llm_request_raw"
    assert replay["events"][1]["event_type"] == "llm_response_raw"
