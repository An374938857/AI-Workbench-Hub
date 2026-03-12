from __future__ import annotations

import re

from app.services.sandbox_archive_service import SandboxArchiveMember

_INVALID_ARCHIVE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_archive_label(value: str | None, fallback: str, max_length: int = 120) -> str:
    text = (value or "").strip()
    if not text:
        return fallback

    cleaned = _INVALID_ARCHIVE_CHARS.sub("_", text)
    cleaned = cleaned.strip()
    if not cleaned or cleaned in {".", ".."}:
        return fallback
    return cleaned[:max_length]


def wrap_members_with_root(
    members: list[SandboxArchiveMember],
    root_label: str,
) -> list[SandboxArchiveMember]:
    wrapped: list[SandboxArchiveMember] = []
    safe_root = root_label.replace("\\", "/").strip("/")

    for item in members:
        relative_path = (item.archive_path or "").replace("\\", "/").lstrip("/")
        archive_path = f"{safe_root}/{relative_path}" if relative_path else safe_root
        wrapped.append(
            SandboxArchiveMember(
                archive_path=archive_path,
                file_path=item.file_path,
                content_bytes=item.content_bytes,
            )
        )
    return wrapped
