"""
沙箱文件管理器
实现对话级别的文件沙箱隔离
"""
import logging
import os
import re
import shutil
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.uploaded_file import UploadedFile

logger = logging.getLogger(__name__)

# 默认沙箱空间限制：100MB
DEFAULT_SANDBOX_SIZE_LIMIT = 100 * 1024 * 1024  # 100MB

# 沙箱默认子目录（仅用于初始化）
SANDBOX_SUBDIRS = ["uploads", "generated", "skills"]
LEGACY_SKILL_SUBDIR = "references"
SKILL_SUBDIR = "skills"

# 禁止的文件名模式
FORBIDDEN_PATTERNS = ["..", "~", "//", "\\\\"]


class SandboxFileManager:
    """沙箱文件管理器"""

    def __init__(self, settings: Any = None):
        self.settings = settings or get_settings()
        self.sandbox_base_dir = os.path.join(self.settings.UPLOAD_DIR, "sandbox")
        os.makedirs(self.sandbox_base_dir, exist_ok=True)

    def get_sandbox_path(self, conversation_id: int) -> str:
        """
        获取对话的沙箱路径

        Args:
            conversation_id: 对话 ID

        Returns:
            沙箱目录绝对路径
        """
        return os.path.join(self.sandbox_base_dir, str(conversation_id))

    def init_sandbox(self, conversation_id: int) -> str:
        """
        初始化沙箱目录

        Args:
            conversation_id: 对话 ID

        Returns:
            沙箱目录绝对路径
        """
        sandbox_path = self.get_sandbox_path(conversation_id)

        # 创建沙箱目录及子目录（幂等，兼容已有沙箱目录）
        if os.path.exists(sandbox_path):
            logger.debug(f"沙箱目录已存在: {sandbox_path}")

        os.makedirs(sandbox_path, exist_ok=True)
        for subdir in SANDBOX_SUBDIRS:
            os.makedirs(os.path.join(sandbox_path, subdir), exist_ok=True)

        logger.info(f"初始化沙箱目录: {sandbox_path}")
        return sandbox_path

    def _validate_filename(self, filename: str) -> None:
        """
        验证文件名安全性

        Args:
            filename: 文件名

        Raises:
            ValueError: 文件名包含非法字符或模式
        """
        if not filename or not isinstance(filename, str):
            raise ValueError("文件名不能为空")

        # 检查禁止的模式
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in filename:
                raise ValueError(f"文件名包含非法模式: {pattern}")

        # 检查是否是绝对路径
        if os.path.isabs(filename):
            raise ValueError("不允许使用绝对路径")

        # 检查路径遍历
        if filename.startswith("/") or filename.startswith("\\"):
            raise ValueError("不允许使用路径分隔符开头")

    def _get_file_path(self, conversation_id: int, filename: str, subdir: str = "") -> str:
        """
        获取文件在沙箱中的完整路径

        Args:
            conversation_id: 对话 ID
            filename: 文件名
            subdir: 子目录（可选，支持嵌套路径）

        Returns:
            文件完整路径

        Raises:
            ValueError: 文件名非法
        """
        normalized_subdir, normalized_filename = self._normalize_subdir_and_filename(
            conversation_id, subdir, filename
        )
        self._validate_filename(normalized_filename)
        if normalized_subdir:
            self._validate_filename(normalized_subdir)
            combined_relative_path = (
                f"{normalized_subdir.rstrip('/')}/{normalized_filename.lstrip('/')}"
            )
        else:
            combined_relative_path = normalized_filename

        file_path, _ = self.resolve_sandbox_relative_path(
            conversation_id, combined_relative_path
        )
        return file_path

    @staticmethod
    def _normalize_relative_arg(value: Optional[str]) -> str:
        if value is None:
            return ""
        normalized = str(value).strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized.strip("/")

    def _normalize_subdir_and_filename(
        self,
        conversation_id: int,
        subdir: Optional[str],
        filename: str,
    ) -> tuple[str, str]:
        normalized_subdir = self._normalize_relative_arg(subdir)
        normalized_filename = self._normalize_relative_arg(filename)

        sandbox_prefix = f"sandbox/{conversation_id}/"
        if normalized_subdir.startswith(sandbox_prefix):
            normalized_subdir = normalized_subdir[len(sandbox_prefix):]
        marker = f"/sandbox/{conversation_id}/"
        if marker in normalized_subdir:
            normalized_subdir = normalized_subdir.split(marker, 1)[1]
        normalized_subdir = normalized_subdir.strip("/")

        if not normalized_filename:
            return normalized_subdir, normalized_filename

        if normalized_filename.startswith(sandbox_prefix):
            normalized_filename = normalized_filename[len(sandbox_prefix):]
        if marker in normalized_filename:
            normalized_filename = normalized_filename.split(marker, 1)[1]
        normalized_filename = normalized_filename.strip("/")

        if normalized_subdir:
            subdir_prefix = f"{normalized_subdir}/"
            if normalized_filename.startswith(subdir_prefix):
                normalized_filename = normalized_filename[len(subdir_prefix):]
            elif normalized_subdir.startswith(f"{SKILL_SUBDIR}/"):
                # 兼容模型把挂载目录同时写到 subdir 和 filename 的情况
                skill_mount_prefix = normalized_subdir[len(SKILL_SUBDIR) + 1 :].strip("/")
                if skill_mount_prefix and normalized_filename.startswith(
                    f"{skill_mount_prefix}/"
                ):
                    normalized_filename = normalized_filename[len(skill_mount_prefix) + 1 :]

        return normalized_subdir, normalized_filename

    def _normalize_list_subdir(
        self,
        conversation_id: int,
        subdir: Optional[str],
    ) -> Optional[str]:
        if subdir is None:
            return None
        normalized_subdir = self._normalize_relative_arg(subdir)
        if not normalized_subdir:
            return None
        sandbox_prefix = f"sandbox/{conversation_id}/"
        if normalized_subdir.startswith(sandbox_prefix):
            normalized_subdir = normalized_subdir[len(sandbox_prefix):]
        return normalized_subdir

    def resolve_sandbox_relative_path(
        self, conversation_id: int, relative_path: str
    ) -> tuple[str, str]:
        """
        将沙箱相对路径解析为安全的绝对路径。

        Args:
            conversation_id: 对话 ID
            relative_path: 沙箱内相对路径

        Returns:
            (absolute_path, normalized_relative_path)
        """
        self._validate_filename(relative_path)

        normalized_path = os.path.normpath(relative_path).replace("\\", "/")
        if normalized_path in {"", ".", "/"}:
            raise ValueError("目录路径不能为空")

        sandbox_path = os.path.abspath(self.get_sandbox_path(conversation_id))
        target_path = os.path.abspath(os.path.join(sandbox_path, normalized_path))
        if os.path.commonpath([sandbox_path, target_path]) != sandbox_path:
            raise ValueError("目录路径非法")

        return target_path, normalized_path

    @staticmethod
    def _sanitize_mount_name(name: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-._")
        return sanitized or "skill"

    @classmethod
    def resolve_skill_mount_dirname(
        cls,
        package_path: Optional[str],
        skill_name: Optional[str] = None,
    ) -> str:
        """
        解析技能在沙箱中的挂载目录名。

        优先级：
        1. SKILL.md frontmatter 中的 name
        2. package_path 目录名（排除明显的中间目录名）
        3. Skill 名称
        4. 默认 skill
        """
        if package_path and os.path.isdir(package_path):
            skill_md_path = os.path.join(package_path, "SKILL.md")
            if os.path.isfile(skill_md_path):
                try:
                    with open(skill_md_path, "r", encoding="utf-8") as f:
                        content = f.read(2048)
                    frontmatter_match = re.match(
                        r"^---\s*\n(.*?)\n---\s*\n",
                        content,
                        re.DOTALL,
                    )
                    if frontmatter_match:
                        name_match = re.search(
                            r"^name:\s*(.+?)\s*$",
                            frontmatter_match.group(1),
                            re.MULTILINE,
                        )
                        if name_match:
                            return cls._sanitize_mount_name(name_match.group(1))
                except Exception:
                    logger.debug("读取 SKILL.md frontmatter 失败", exc_info=True)

            base_name = os.path.basename(os.path.normpath(package_path))
            if base_name and base_name.lower() not in {"files", "package", "packages"}:
                return cls._sanitize_mount_name(base_name)

        if skill_name:
            return cls._sanitize_mount_name(skill_name)

        return "skill"

    def copy_skill_directory(
        self,
        conversation_id: int,
        skill_id: int,
        package_path: Optional[str],
        skill_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        将 Skill 包目录复制到对话沙箱 skills/<mount_dirname>/ 下。

        Args:
            conversation_id: 对话 ID
            skill_id: Skill ID
            package_path: 技能包解压目录

        Returns:
            {
                "success": bool,
                "message": str,
                "path": Optional[str]
            }
        """
        if not package_path:
            return {
                "success": False,
                "message": "Skill 包目录为空",
                "path": None,
            }

        if not os.path.isdir(package_path):
            return {
                "success": False,
                "message": f"Skill 包目录不存在: {package_path}",
                "path": None,
            }

        self.init_sandbox(conversation_id)
        mount_dirname = self.resolve_skill_mount_dirname(package_path, skill_name)
        target_dir = self._get_file_path(
            conversation_id, mount_dirname, SKILL_SUBDIR
        )
        legacy_target_dir = self._get_file_path(
            conversation_id, mount_dirname, LEGACY_SKILL_SUBDIR
        )

        try:
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            shutil.copytree(package_path, target_dir)
            if os.path.exists(legacy_target_dir):
                shutil.rmtree(legacy_target_dir)
            logger.info(
                "复制 Skill 目录到沙箱成功: conversation_id=%s, skill_id=%s, target=%s",
                conversation_id,
                skill_id,
                target_dir,
            )
            return {
                "success": True,
                "message": "Skill 目录复制成功",
                "path": target_dir,
            }
        except Exception as e:
            logger.error(
                "复制 Skill 目录到沙箱失败: conversation_id=%s, skill_id=%s, error=%s",
                conversation_id,
                skill_id,
                e,
                exc_info=True,
            )
            return {
                "success": False,
                "message": f"复制 Skill 目录失败: {str(e)}",
                "path": None,
            }

    def create_file(
        self,
        conversation_id: int,
        filename: str,
        content: str,
        subdir: str = "",
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        创建文件

        Args:
            conversation_id: 对话 ID
            filename: 文件名
            content: 文件内容
            subdir: 子目录（支持任意相对路径）
            overwrite: 是否覆盖已存在的文件

        Returns:
            {
                "success": bool,
                "message": str,
                "path": str,
                "size": int
            }
        """
        try:
            # 确保沙箱存在
            self.init_sandbox(conversation_id)
            new_file_size = len(content.encode("utf-8"))

            file_path = self._get_file_path(conversation_id, filename, subdir)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # 检查文件是否已存在
            if os.path.exists(file_path) and not overwrite:
                return {
                    "success": False,
                    "message": f"文件已存在: {filename}",
                    "path": file_path,
                    "size": 0
                }

            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"创建文件: {file_path} ({new_file_size} bytes)")

            return {
                "success": True,
                "message": "文件创建成功",
                "path": file_path,
                "size": new_file_size
            }

        except Exception as e:
            logger.error(f"创建文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"创建文件失败: {str(e)}",
                "path": None,
                "size": 0
            }

    def create_file_binary(
        self,
        conversation_id: int,
        filename: str,
        content: bytes,
        subdir: str = "",
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        创建文件（二进制模式，适用于图片等）

        Args:
            conversation_id: 对话 ID
            filename: 文件名
            content: 文件内容（字节）
            subdir: 子目录（支持任意相对路径）
            overwrite: 是否覆盖已存在的文件

        Returns:
            {
                "success": bool,
                "message": str,
                "path": str,
                "size": int
            }
        """
        try:
            # 确保沙箱存在
            self.init_sandbox(conversation_id)
            new_file_size = len(content)

            file_path = self._get_file_path(conversation_id, filename, subdir)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # 检查文件是否已存在
            if os.path.exists(file_path) and not overwrite:
                return {
                    "success": False,
                    "message": f"文件已存在: {filename}",
                    "path": file_path,
                    "size": 0
                }

            # 写入文件（二进制模式）
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(f"创建二进制文件: {file_path} ({new_file_size} bytes)")

            return {
                "success": True,
                "message": "文件创建成功",
                "path": file_path,
                "size": new_file_size
            }

        except Exception as e:
            logger.error(f"创建二进制文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"创建文件失败: {str(e)}",
                "path": None,
                "size": 0
            }

    def read_file(
        self,
        conversation_id: int,
        filename: str,
        subdir: str = ""
    ) -> Dict[str, Any]:
        """
        读取文件

        Args:
            conversation_id: 对话 ID
            filename: 文件名
            subdir: 子目录

        Returns:
            {
                "success": bool,
                "message": str,
                "content": str,
                "size": int
            }
        """
        try:
            normalized_subdir, normalized_filename = self._normalize_subdir_and_filename(
                conversation_id, subdir, filename
            )
            requested_sandbox_path = (
                f"{normalized_subdir.rstrip('/')}/{normalized_filename.lstrip('/')}"
                if normalized_subdir
                else normalized_filename
            ).strip("/")
            file_path = self._get_file_path(conversation_id, filename, subdir)
            sandbox_path = self.get_sandbox_path(conversation_id)
            resolved_sandbox_path = None
            used_fallback_resolution = False

            if not os.path.exists(file_path) and subdir == SKILL_SUBDIR:
                # 兼容历史会话：旧技能目录在 references/
                legacy_file_path = self._get_file_path(
                    conversation_id, filename, LEGACY_SKILL_SUBDIR
                )
                if os.path.exists(legacy_file_path):
                    file_path = legacy_file_path
                    used_fallback_resolution = True

            if not os.path.exists(file_path):
                # 兜底：当路径参数不正确时，按文件名在整个对话沙箱中检索
                target_name = os.path.basename(self._normalize_relative_arg(filename))
                matched_paths: List[str] = []
                if target_name and os.path.exists(sandbox_path):
                    for root, _, filenames in os.walk(sandbox_path):
                        if target_name in filenames:
                            matched_paths.append(os.path.join(root, target_name))

                if len(matched_paths) == 1:
                    file_path = matched_paths[0]
                    resolved_sandbox_path = os.path.relpath(
                        file_path, sandbox_path
                    ).replace("\\", "/")
                    used_fallback_resolution = True
                elif len(matched_paths) > 1:
                    candidates = [
                        os.path.relpath(path, sandbox_path).replace("\\", "/")
                        for path in matched_paths[:10]
                    ]
                    return {
                        "success": False,
                        "message": (
                            "文件路径不正确，且存在多个同名文件，无法自动判定。"
                            f"请使用更精确的 subdir/filename。候选路径: {', '.join(candidates)}"
                        ),
                        "content": None,
                        "size": 0
                    }

            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "message": f"文件不存在: {filename}",
                    "content": None,
                    "size": 0
                }

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            file_size = os.path.getsize(file_path)
            if resolved_sandbox_path is None:
                resolved_sandbox_path = os.path.relpath(
                    file_path, sandbox_path
                ).replace("\\", "/")

            if used_fallback_resolution or (
                requested_sandbox_path and resolved_sandbox_path != requested_sandbox_path
            ):
                read_message = (
                    "文件读取成功（路径自动纠正）: "
                    f"原请求 `{filename}`，实际读取 `{resolved_sandbox_path}`。"
                )
            else:
                read_message = "文件读取成功"

            return {
                "success": True,
                "message": read_message,
                "content": content,
                "size": file_size,
                "resolved_path": resolved_sandbox_path,
            }

        except Exception as e:
            logger.error(f"读取文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"读取文件失败: {str(e)}",
                "content": None,
                "size": 0
            }

    def update_file(
        self,
        conversation_id: int,
        filename: str,
        content: str,
        subdir: str = ""
    ) -> Dict[str, Any]:
        """
        更新文件

        Args:
            conversation_id: 对话 ID
            filename: 文件名
            content: 新内容
            subdir: 子目录

        Returns:
            {
                "success": bool,
                "message": str,
                "size": int
            }
        """
        return self.create_file(conversation_id, filename, content, subdir, overwrite=True)

    def delete_file(
        self,
        conversation_id: int,
        filename: str,
        subdir: str = ""
    ) -> Dict[str, Any]:
        """
        删除文件

        Args:
            conversation_id: 对话 ID
            filename: 文件名
            subdir: 子目录

        Returns:
            {
                "success": bool,
                "message": str
            }
        """
        try:
            file_path = self._get_file_path(conversation_id, filename, subdir)

            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "message": f"文件不存在: {filename}"
                }

            os.remove(file_path)

            logger.info(f"删除文件: {file_path}")

            return {
                "success": True,
                "message": "文件删除成功"
            }

        except Exception as e:
            logger.error(f"删除文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"删除文件失败: {str(e)}"
            }

    def delete_directory(
        self,
        conversation_id: int,
        relative_path: str
    ) -> Dict[str, Any]:
        """
        递归删除沙箱目录。

        Args:
            conversation_id: 对话 ID
            relative_path: 沙箱内目录相对路径

        Returns:
            {
                "success": bool,
                "message": str
            }
        """
        try:
            directory_path, normalized_path = self.resolve_sandbox_relative_path(
                conversation_id, relative_path
            )

            if not os.path.exists(directory_path):
                return {
                    "success": False,
                    "message": f"目录不存在: {normalized_path}"
                }

            if not os.path.isdir(directory_path):
                return {
                    "success": False,
                    "message": f"目标不是目录: {normalized_path}"
                }

            shutil.rmtree(directory_path)
            logger.info(f"删除目录: {directory_path}")

            return {
                "success": True,
                "message": "目录删除成功"
            }
        except Exception as e:
            logger.error(f"删除目录失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"删除目录失败: {str(e)}"
            }

    def list_files(
        self,
        conversation_id: int,
        subdir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        列出沙箱中的文件

        Args:
            conversation_id: 对话 ID
            subdir: 子目录（可选，支持任意相对路径；不指定则遍历整个沙箱）

        Returns:
            {
                "success": bool,
                "message": str,
                "files": List[Dict],
                "total_size": int
            }
        """
        try:
            sandbox_path = self.get_sandbox_path(conversation_id)

            if not os.path.exists(sandbox_path):
                return {
                    "success": True,
                    "message": "沙箱为空",
                    "files": [],
                    "total_size": 0
                }

            files = []
            total_size = 0

            normalized_subdir = self._normalize_list_subdir(conversation_id, subdir)

            if normalized_subdir:
                # 列出指定子目录的文件（任意相对路径）
                dir_path, normalized_subdir = self.resolve_sandbox_relative_path(
                    conversation_id, normalized_subdir
                )
                walk_targets: List[tuple[str, str]] = []
                if os.path.exists(dir_path):
                    walk_targets.append((dir_path, normalized_subdir))

                if normalized_subdir == SKILL_SUBDIR:
                    # 兼容历史会话：旧技能目录在 references/
                    legacy_dir_path, legacy_subdir = self.resolve_sandbox_relative_path(
                        conversation_id, LEGACY_SKILL_SUBDIR
                    )
                    if os.path.exists(legacy_dir_path):
                        walk_targets.append((legacy_dir_path, legacy_subdir))

                if not walk_targets:
                    return {
                        "success": True,
                        "message": "目录为空",
                        "files": [],
                        "total_size": 0
                    }

                for current_dir_path, current_subdir in walk_targets:
                    if not os.path.isdir(current_dir_path):
                        return {
                            "success": False,
                            "message": f"目标不是目录: {current_subdir}",
                            "files": [],
                            "total_size": 0
                        }
                    for root, _, filenames in os.walk(current_dir_path):
                        for item in filenames:
                            item_path = os.path.join(root, item)
                            rel_path = os.path.relpath(item_path, current_dir_path)
                            file_size = os.path.getsize(item_path)
                            files.append({
                                "filename": item,
                                "relative_path": rel_path,
                                "sandbox_path": os.path.join(current_subdir, rel_path),
                                "subdir": current_subdir,
                                "size": file_size,
                                "modified_at": os.path.getmtime(item_path)
                            })
                            total_size += file_size
            else:
                # 列出整个沙箱的文件（不限固定子目录）
                for root, _, filenames in os.walk(sandbox_path):
                    for item in filenames:
                        item_path = os.path.join(root, item)
                        sandbox_rel_path = os.path.relpath(item_path, sandbox_path)
                        file_size = os.path.getsize(item_path)
                        rel_parts = sandbox_rel_path.split(os.sep, 1)
                        top_level_subdir = rel_parts[0] if len(rel_parts) > 1 else ""
                        relative_path = rel_parts[1] if len(rel_parts) > 1 else rel_parts[0]
                        files.append({
                            "filename": item,
                            "relative_path": relative_path,
                            "sandbox_path": sandbox_rel_path.replace("\\", "/"),
                            "subdir": top_level_subdir,
                            "size": file_size,
                            "modified_at": os.path.getmtime(item_path)
                        })
                        total_size += file_size

            # 按修改时间排序（最新的在前）
            files.sort(key=lambda x: x["modified_at"], reverse=True)

            return {
                "success": True,
                "message": f"找到 {len(files)} 个文件",
                "files": files,
                "total_size": total_size
            }

        except Exception as e:
            logger.error(f"列出文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"列出文件失败: {str(e)}",
                "files": [],
                "total_size": 0
            }

    def get_sandbox_size(self, conversation_id: int) -> int:
        """
        获取沙箱总大小

        Args:
            conversation_id: 对话 ID

        Returns:
            沙箱总大小（字节）
        """
        sandbox_path = self.get_sandbox_path(conversation_id)

        if not os.path.exists(sandbox_path):
            return 0

        total_size = 0
        for root, dirs, files in os.walk(sandbox_path):
            for file in files:
                file_path = os.path.join(root, file)
                if os.path.isfile(file_path):
                    total_size += os.path.getsize(file_path)

        return total_size

    def cleanup_sandbox(self, conversation_id: int) -> Dict[str, Any]:
        """
        清理沙箱

        Args:
            conversation_id: 对话 ID

        Returns:
            {
                "success": bool,
                "message": str,
                "freed_size": int
            }
        """
        try:
            sandbox_path = self.get_sandbox_path(conversation_id)

            if not os.path.exists(sandbox_path):
                return {
                    "success": True,
                    "message": "沙箱不存在，无需清理",
                    "freed_size": 0
                }

            # 计算释放的空间
            freed_size = self.get_sandbox_size(conversation_id)

            # 删除整个沙箱目录
            shutil.rmtree(sandbox_path)

            logger.info(f"清理沙箱: {sandbox_path} (释放 {freed_size} bytes)")

            return {
                "success": True,
                "message": f"沙箱清理成功（释放 {freed_size / 1024 / 1024:.2f}MB）",
                "freed_size": freed_size
            }

        except Exception as e:
            logger.error(f"清理沙箱失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"清理沙箱失败: {str(e)}",
                "freed_size": 0
            }

    def move_uploaded_to_sandbox(
        self,
        uploaded_file: UploadedFile,
        db: Session
    ) -> bool:
        """
        将已上传的文件移动到沙箱

        Args:
            uploaded_file: UploadedFile 对象
            db: 数据库会话

        Returns:
            是否成功
        """
        try:
            if not uploaded_file.conversation_id:
                logger.warning(f"文件 {uploaded_file.id} 没有关联对话，跳过移动")
                return False

            # 确保沙箱存在
            self.init_sandbox(uploaded_file.conversation_id)

            # 检查文件是否已移动
            if uploaded_file.sandbox_path:
                logger.debug(f"文件 {uploaded_file.id} 已在沙箱中: {uploaded_file.sandbox_path}")
                return True

            # 检查源文件是否存在
            if not os.path.exists(uploaded_file.stored_path):
                logger.warning(f"源文件不存在: {uploaded_file.stored_path}")
                return False

            # 目标路径
            target_subdir = "uploads" if uploaded_file.source == "upload" else "generated"
            target_filename = uploaded_file.original_name
            target_path = self._get_file_path(
                uploaded_file.conversation_id,
                target_filename,
                target_subdir
            )

            # 移动文件
            shutil.move(uploaded_file.stored_path, target_path)

            # 更新数据库
            uploaded_file.sandbox_path = os.path.join(target_subdir, target_filename)
            uploaded_file.stored_path = target_path
            db.commit()

            logger.info(f"移动文件到沙箱: {uploaded_file.id} -> {target_path}")
            return True

        except Exception as e:
            logger.error(f"移动文件到沙箱失败: {e}", exc_info=True)
            db.rollback()
            return False

    @staticmethod
    def _infer_source_by_subdir(subdir: str) -> str:
        if subdir == "uploads":
            return "upload"
        if subdir in {SKILL_SUBDIR, LEGACY_SKILL_SUBDIR}:
            return "reference"
        return "generated"

    def reconcile_sandbox_files(
        self,
        conversation_id: int,
        user_id: int,
        db: Session,
    ) -> Dict[str, Any]:
        """
        以实际磁盘内容为准，对账 uploaded_files 记录并返回当前沙箱文件列表。

        Returns:
            {
                "success": bool,
                "message": str,
                "files": List[Dict[str, Any]],
                "total_size": int,
                "created_count": int,
                "updated_count": int,
                "deleted_count": int,
            }
        """
        try:
            scan_result = self.list_files(conversation_id)
            if not scan_result["success"]:
                return {
                    "success": False,
                    "message": scan_result["message"],
                    "files": [],
                    "total_size": 0,
                    "created_count": 0,
                    "updated_count": 0,
                    "deleted_count": 0,
                }

            existing_records = (
                db.query(UploadedFile)
                .filter(UploadedFile.conversation_id == conversation_id)
                .order_by(UploadedFile.id.asc())
                .all()
            )

            records_by_path: dict[str, UploadedFile] = {}
            duplicate_records: list[UploadedFile] = []
            for record in existing_records:
                normalized_path = (record.sandbox_path or "").replace("\\", "/")
                if not normalized_path:
                    duplicate_records.append(record)
                    continue
                if normalized_path in records_by_path:
                    duplicate_records.append(record)
                    continue
                records_by_path[normalized_path] = record

            for duplicate in duplicate_records:
                db.delete(duplicate)

            created_count = 0
            updated_count = 0
            deleted_count = len(duplicate_records)
            scanned_paths: set[str] = set()
            reconciled_files: list[dict[str, Any]] = []

            for file_info in scan_result["files"]:
                filename = file_info["filename"]
                subdir = file_info["subdir"]
                relative_path = file_info.get("relative_path") or filename
                sandbox_path = (
                    str(file_info.get("sandbox_path") or os.path.join(subdir, relative_path))
                    .replace("\\", "/")
                )
                file_path = self._get_file_path(conversation_id, relative_path, subdir)
                file_type = (
                    filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                )
                source = self._infer_source_by_subdir(subdir)
                modified_at = datetime.fromtimestamp(file_info["modified_at"])
                scanned_paths.add(sandbox_path)

                record = records_by_path.get(sandbox_path)
                if record is None:
                    record = UploadedFile(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=None,
                        source=source,
                        original_name=filename,
                        stored_path=file_path,
                        file_size=file_info["size"],
                        file_type=file_type,
                        sandbox_path=sandbox_path,
                        created_at=modified_at,
                    )
                    db.add(record)
                    db.flush()
                    records_by_path[sandbox_path] = record
                    created_count += 1
                else:
                    changed = False
                    if record.user_id != user_id:
                        record.user_id = user_id
                        changed = True
                    if record.original_name != filename:
                        record.original_name = filename
                        changed = True
                    if record.stored_path != file_path:
                        record.stored_path = file_path
                        changed = True
                    if record.file_size != file_info["size"]:
                        record.file_size = file_info["size"]
                        changed = True
                    if record.file_type != file_type:
                        record.file_type = file_type
                        changed = True
                    if record.source != source:
                        record.source = source
                        changed = True
                    if (record.sandbox_path or "").replace("\\", "/") != sandbox_path:
                        record.sandbox_path = sandbox_path
                        changed = True
                    if changed:
                        updated_count += 1

                reconciled_files.append(
                    {
                        "file_id": record.id,
                        "filename": filename,
                        "original_name": record.original_name,
                        "file_size": record.file_size,
                        "file_type": record.file_type,
                        "source": record.source,
                        "sandbox_path": record.sandbox_path,
                        "created_at": record.created_at or modified_at,
                    }
                )

            for sandbox_path, record in list(records_by_path.items()):
                if sandbox_path in scanned_paths:
                    continue
                db.delete(record)
                deleted_count += 1

            db.commit()

            return {
                "success": True,
                "message": (
                    f"对账完成（新增 {created_count}，更新 {updated_count}，删除 {deleted_count}）"
                ),
                "files": reconciled_files,
                "total_size": scan_result["total_size"],
                "created_count": created_count,
                "updated_count": updated_count,
                "deleted_count": deleted_count,
            }
        except Exception as e:
            logger.error(f"沙箱文件对账失败: {e}", exc_info=True)
            db.rollback()
            return {
                "success": False,
                "message": f"沙箱文件对账失败: {str(e)}",
                "files": [],
                "total_size": 0,
                "created_count": 0,
                "updated_count": 0,
                "deleted_count": 0,
            }

    def sync_sandbox_to_db(
        self,
        conversation_id: int,
        user_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        同步沙箱文件到数据库

        Args:
            conversation_id: 对话 ID
            user_id: 用户 ID
            db: 数据库会话

        Returns:
            {
                "success": bool,
                "message": str,
                "synced_count": int
            }
        """
        result = self.reconcile_sandbox_files(conversation_id, user_id, db)
        if not result["success"]:
            return {
                "success": False,
                "message": result["message"],
                "synced_count": 0
            }
        synced_count = int(result["created_count"]) + int(result["updated_count"])
        logger.info(
            "同步沙箱文件到数据库: conversation_id=%s, created=%s, updated=%s, deleted=%s",
            conversation_id,
            result["created_count"],
            result["updated_count"],
            result["deleted_count"],
        )
        return {
            "success": True,
            "message": result["message"],
            "synced_count": synced_count,
        }
