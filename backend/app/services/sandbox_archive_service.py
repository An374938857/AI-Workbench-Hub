from __future__ import annotations

import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Iterable


@dataclass(slots=True)
class SandboxArchiveMember:
    archive_path: str
    file_path: str | None = None
    content_bytes: bytes | None = None


class SandboxArchiveService:
    def __init__(self, tmp_dir: str | None = None):
        self.tmp_dir = tmp_dir or tempfile.gettempdir()
        os.makedirs(self.tmp_dir, exist_ok=True)

    @staticmethod
    def _normalize_archive_path(path: str) -> str:
        candidate = (path or "").strip().replace("\\", "/")
        if not candidate:
            raise ValueError("压缩包路径非法：不能为空")

        normalized = str(PurePosixPath(candidate))
        normalized = normalized.strip("/")
        if not normalized or normalized in {".", ".."}:
            raise ValueError("压缩包路径非法：不能为空目录")
        if normalized.startswith("../") or "/../" in normalized:
            raise ValueError("压缩包路径非法：包含路径穿越")
        if normalized.startswith("/"):
            raise ValueError("压缩包路径非法：不允许绝对路径")
        return normalized

    @staticmethod
    def _ensure_zip_filename(filename: str) -> str:
        cleaned = (filename or "sandbox_archive").strip().replace("/", "_").replace("\\", "_")
        if not cleaned.lower().endswith(".zip"):
            cleaned = f"{cleaned}.zip"
        return cleaned

    @staticmethod
    def _add_directory_entries(zf: zipfile.ZipFile, file_paths: Iterable[str]) -> None:
        dir_entries: set[str] = set()
        for path in file_paths:
            parts = path.split("/")
            for idx in range(1, len(parts)):
                dir_entries.add("/".join(parts[:idx]) + "/")
        for dir_entry in sorted(dir_entries):
            zf.writestr(dir_entry, b"")

    @staticmethod
    def _unique_archive_path(path: str, occupied: set[str]) -> str:
        if path not in occupied:
            return path

        stem, ext = os.path.splitext(path)
        index = 1
        while True:
            candidate = f"{stem} ({index}){ext}"
            if candidate not in occupied:
                return candidate
            index += 1

    def create_archive(self, members: list[SandboxArchiveMember], archive_filename: str) -> str:
        normalized_members: list[SandboxArchiveMember] = []
        occupied_paths: set[str] = set()

        for item in members:
            if not item.file_path and item.content_bytes is None:
                raise ValueError("压缩成员非法：file_path 或 content_bytes 必须提供")

            normalized_path = self._normalize_archive_path(item.archive_path)
            normalized_path = self._unique_archive_path(normalized_path, occupied_paths)
            occupied_paths.add(normalized_path)

            normalized_members.append(
                SandboxArchiveMember(
                    archive_path=normalized_path,
                    file_path=item.file_path,
                    content_bytes=item.content_bytes,
                )
            )

        safe_name = self._ensure_zip_filename(archive_filename)
        target_path = os.path.join(
            self.tmp_dir,
            f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}_{safe_name}",
        )

        with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            self._add_directory_entries(zf, [item.archive_path for item in normalized_members])
            for item in normalized_members:
                if item.file_path:
                    if not os.path.exists(item.file_path) or not os.path.isfile(item.file_path):
                        raise FileNotFoundError(f"文件不存在: {item.file_path}")
                    zf.write(item.file_path, arcname=item.archive_path)
                else:
                    zf.writestr(item.archive_path, item.content_bytes or b"")

        return target_path

    @staticmethod
    def cleanup_file(file_path: str) -> None:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            # 清理失败不影响主流程
            pass
