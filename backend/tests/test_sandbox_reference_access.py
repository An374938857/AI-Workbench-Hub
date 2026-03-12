import os
import sys
import tempfile
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.mcp.handlers.sandbox_file_handler import SandboxFileHandler
from app.models.asset import Asset
from app.models.conversation import Conversation
from app.models.reference import ConversationReferenceState
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.services.reference_service import SANDBOX_FILE_ID_OFFSET


def _new_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    return SessionLocal()


def test_sandbox_tools_can_read_selected_reference_files_without_mirroring():
    session = _new_session()
    try:
        user = User(username="u1", password_hash="pwd", display_name="User1", role="user")
        session.add(user)
        session.flush()

        conv = Conversation(user_id=user.id, title="chat")
        source_conv = Conversation(user_id=user.id, title="source")
        session.add_all([conv, source_conv])
        session.flush()

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fp:
            fp.write("引用文件正文")
            source_path = fp.name

        uploaded = UploadedFile(
            conversation_id=source_conv.id,
            user_id=user.id,
            original_name="实施计划.md",
            stored_path=source_path,
            file_size=24,
            file_type="md",
            extracted_text="实施计划摘要",
            source="generated",
            sandbox_path="generated/实施计划.md",
            created_at=datetime.now(),
        )
        session.add(uploaded)
        session.flush()

        state = ConversationReferenceState(
            conversation_id=conv.id,
            selected_file_ids=[SANDBOX_FILE_ID_OFFSET + uploaded.id],
            empty_mode="none",
            selection_version=1,
            updated_by=user.id,
            updated_at=datetime.now(),
        )
        session.add(state)

        asset = Asset(
            scope_type="PROJECT",
            scope_id=1,
            node_code="N1",
            asset_type="MARKDOWN",
            title="需求说明",
            content="# 需求说明\n内容A",
            snapshot_markdown="# 需求说明\n内容A",
            file_ref=None,
            created_by=user.id,
        )
        session.add(asset)
        session.flush()
        state.selected_file_ids = state.selected_file_ids + [asset.id]
        session.commit()

        handler = SandboxFileHandler(db=session)

        list_result = handler.handle_tool_call("sandbox_list_files", {}, conv.id)
        assert list_result["success"] is True
        assert "references/CONVERSATION" in list_result["content"]
        assert "references/ASSET" in list_result["content"]

        read_result = handler.handle_tool_call(
            "sandbox_read_file",
            {"filename": f"CONVERSATION/{source_conv.id}/generated/实施计划.md"},
            conv.id,
        )
        assert read_result["success"] is True
        assert "引用文件正文" in read_result["content"]
    finally:
        session.close()
        try:
            os.remove(source_path)
        except Exception:
            pass
