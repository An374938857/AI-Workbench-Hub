import json
from typing import List, Dict, Optional

_encoding = None


def _get_encoding():
    global _encoding
    if _encoding is None:
        import tiktoken
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def count_tokens(text: str) -> int:
    try:
        return len(_get_encoding().encode(text))
    except Exception:
        return len(text) // 4


def count_messages_tokens(messages: List[Dict]) -> int:
    total = 0
    for msg in messages:
        total += 4
        content = msg.get("content") or ""
        total += count_tokens(content)
        if "tool_calls" in msg:
            total += count_tokens(json.dumps(msg["tool_calls"], ensure_ascii=False))
        if msg.get("role") == "tool":
            total += count_tokens(msg.get("tool_call_id", ""))
    total += 2
    return total


def estimate_tools_tokens(tools: Optional[List[Dict]]) -> int:
    if not tools:
        return 0
    return count_tokens(json.dumps(tools, ensure_ascii=False))


def estimate_total_context(messages: List[Dict], tools: Optional[List[Dict]] = None) -> int:
    return count_messages_tokens(messages) + estimate_tools_tokens(tools)
