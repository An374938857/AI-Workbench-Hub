import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sandbox_archive_naming import (
    sanitize_archive_label,
    wrap_members_with_root,
)
from app.services.sandbox_archive_service import SandboxArchiveMember


def test_sanitize_archive_label_replaces_invalid_chars():
    assert sanitize_archive_label('项目:Alpha/2026', fallback="project_1") == "项目_Alpha_2026"


def test_sanitize_archive_label_preserves_underscore():
    assert sanitize_archive_label("项目_A_B", fallback="project_1") == "项目_A_B"


def test_sanitize_archive_label_uses_fallback_when_empty():
    assert sanitize_archive_label("   ", fallback="conversation_10") == "conversation_10"


def test_wrap_members_with_root_adds_top_level_directory():
    members = [
        SandboxArchiveMember(archive_path="需求文件/spec.md", file_path="/tmp/spec.md"),
        SandboxArchiveMember(archive_path="需求文件/data/result.json", file_path="/tmp/result.json"),
    ]

    wrapped = wrap_members_with_root(members, "需求A")

    assert wrapped[0].archive_path == "需求A/需求文件/spec.md"
    assert wrapped[1].archive_path == "需求A/需求文件/data/result.json"
