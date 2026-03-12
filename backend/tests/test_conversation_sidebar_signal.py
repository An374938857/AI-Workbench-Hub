import os
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.conversation_sidebar_signal import (  # noqa: E402
    SIDEBAR_SIGNAL_NONE,
    SIDEBAR_SIGNAL_RUNNING,
    SIDEBAR_SIGNAL_UNREAD_REPLY,
    apply_sidebar_signal,
    apply_sidebar_signal_read,
    serialize_sidebar_signal,
)


def make_conversation():
    return SimpleNamespace(
        sidebar_signal_state=SIDEBAR_SIGNAL_NONE,
        sidebar_signal_updated_at=None,
        sidebar_signal_read_at=None,
    )


def test_apply_sidebar_signal_sets_state_and_clears_read_timestamp():
    conv = make_conversation()
    conv.sidebar_signal_read_at = datetime(2026, 3, 11, 9, 0, 0)

    apply_sidebar_signal(
        conv,
        state=SIDEBAR_SIGNAL_RUNNING,
        event_time=datetime(2026, 3, 11, 9, 5, 0),
    )

    assert conv.sidebar_signal_state == SIDEBAR_SIGNAL_RUNNING
    assert conv.sidebar_signal_updated_at == datetime(2026, 3, 11, 9, 5, 0)
    assert conv.sidebar_signal_read_at is None


def test_apply_sidebar_signal_read_turns_off_signal_and_sets_read_time():
    conv = make_conversation()
    apply_sidebar_signal(
        conv,
        state=SIDEBAR_SIGNAL_UNREAD_REPLY,
        event_time=datetime(2026, 3, 11, 9, 10, 0),
    )

    apply_sidebar_signal_read(conv, read_time=datetime(2026, 3, 11, 9, 12, 0))

    assert conv.sidebar_signal_state == SIDEBAR_SIGNAL_NONE
    assert conv.sidebar_signal_updated_at == datetime(2026, 3, 11, 9, 12, 0)
    assert conv.sidebar_signal_read_at == datetime(2026, 3, 11, 9, 12, 0)


def test_serialize_sidebar_signal_shape():
    conv = make_conversation()
    apply_sidebar_signal(
        conv,
        state=SIDEBAR_SIGNAL_RUNNING,
        event_time=datetime(2026, 3, 11, 9, 20, 0),
    )

    payload = serialize_sidebar_signal(conv)

    assert payload["state"] == SIDEBAR_SIGNAL_RUNNING
    assert payload["updated_at"] == "2026-03-11T09:20:00"
    assert payload["read_at"] is None
