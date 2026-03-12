import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sandbox_archive_service import SandboxArchiveMember, SandboxArchiveService


def test_create_archive_preserves_directory_tree(tmp_path: Path):
    source_root = tmp_path / "src"
    nested_dir = source_root / "需求文件" / "需求级资料"
    nested_dir.mkdir(parents=True)

    file_a = nested_dir / "spec.md"
    file_a.write_text("hello", encoding="utf-8")
    file_b = source_root / "需求文件" / "需求关联对话文件" / "#101 会话" / "output.txt"
    file_b.parent.mkdir(parents=True)
    file_b.write_text("world", encoding="utf-8")

    service = SandboxArchiveService(tmp_dir=str(tmp_path))
    archive_path = service.create_archive(
        [
            SandboxArchiveMember(archive_path="需求文件/需求级资料/spec.md", file_path=str(file_a)),
            SandboxArchiveMember(archive_path="需求文件/需求关联对话文件/#101 会话/output.txt", file_path=str(file_b)),
        ],
        archive_filename="requirement_sandbox.zip",
    )

    with zipfile.ZipFile(archive_path, "r") as zf:
        names = set(zf.namelist())

    assert "需求文件/" in names
    assert "需求文件/需求级资料/" in names
    assert "需求文件/需求级资料/spec.md" in names
    assert "需求文件/需求关联对话文件/#101 会话/output.txt" in names


def test_create_archive_rejects_path_traversal(tmp_path: Path):
    file_a = tmp_path / "a.txt"
    file_a.write_text("x", encoding="utf-8")

    service = SandboxArchiveService(tmp_dir=str(tmp_path))

    try:
        service.create_archive(
            [SandboxArchiveMember(archive_path="../evil.txt", file_path=str(file_a))],
            archive_filename="bad.zip",
        )
    except ValueError as exc:
        assert "非法" in str(exc)
    else:
        raise AssertionError("expected ValueError for traversal path")


def test_create_archive_handles_duplicate_names(tmp_path: Path):
    file_a = tmp_path / "same-a.txt"
    file_b = tmp_path / "same-b.txt"
    file_a.write_text("A", encoding="utf-8")
    file_b.write_text("B", encoding="utf-8")

    service = SandboxArchiveService(tmp_dir=str(tmp_path))
    archive_path = service.create_archive(
        [
            SandboxArchiveMember(archive_path="目录/same.txt", file_path=str(file_a)),
            SandboxArchiveMember(archive_path="目录/same.txt", file_path=str(file_b)),
        ],
        archive_filename="dup.zip",
    )

    with zipfile.ZipFile(archive_path, "r") as zf:
        names = sorted(zf.namelist())
        assert "目录/same.txt" in names
        assert "目录/same (1).txt" in names
