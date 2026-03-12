import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.message_tree import _normalize_tool_call_sequence


def test_normalize_tool_call_sequence_keeps_valid_block():
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "calling tool",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "x", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'},
        {"role": "assistant", "content": "done"},
    ]

    normalized = _normalize_tool_call_sequence(messages)
    assert normalized == messages


def test_normalize_tool_call_sequence_degrades_incomplete_tool_call():
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "calling tool",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "x", "arguments": "{}"},
                }
            ],
        },
        {"role": "assistant", "content": "next"},
    ]

    normalized = _normalize_tool_call_sequence(messages)
    assert normalized == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "calling tool"},
        {"role": "assistant", "content": "next"},
    ]


def test_normalize_tool_call_sequence_drops_orphan_tool_message():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "orphan", "content": "x"},
        {"role": "assistant", "content": "reply"},
    ]

    normalized = _normalize_tool_call_sequence(messages)
    assert normalized == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "reply"},
    ]
