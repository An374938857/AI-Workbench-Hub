"""
沙箱文件操作 MCP 工具处理器
实现沙箱文件操作的 MCP 工具
"""
import json
import logging
import os
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.reference import ConversationReferenceState
from app.models.uploaded_file import UploadedFile
from app.services.reference_service import SANDBOX_FILE_ID_OFFSET
from app.services.sandbox_change_counter import increase_sandbox_unread_change_count
from app.services.sandbox_file_manager import SandboxFileManager

logger = logging.getLogger(__name__)

# 工具定义（JSON 格式）
SANDBOX_TOOLS_DEFINITION = {
    "tools": [
        {
            "name": "sandbox_create_file",
            "description": "在对话沙箱中创建一个新文件。支持使用相对路径创建嵌套目录下的文件，可用于保存生成的内容、代码、文档等。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文件名或相对路径（包含扩展名），例如 reports/weekly.md"
                    },
                    "content": {
                        "type": "string",
                        "description": "文件内容"
                    },
                    "subdir": {
                        "type": "string",
                        "default": "",
                        "description": "子目录（可选，支持任意相对路径），默认为空"
                    }
                },
                "required": ["filename", "content"]
            }
        },
        {
            "name": "sandbox_read_file",
            "description": "从对话沙箱中读取文件内容。支持读取技能目录下任意子目录的相对路径，例如 weekly-report/assets/config.yaml 或 weekly-report/hooks/openclaw/HOOK.md。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文件名或相对路径，例如 weekly-report/assets/config.yaml"
                    },
                    "subdir": {
                        "type": "string",
                        "default": "",
                        "description": "子目录（可选，支持任意相对路径），默认为空"
                    }
                },
                "required": ["filename"]
            }
        },
        {
            "name": "sandbox_update_file",
            "description": "更新对话沙箱中的文件内容。支持使用相对路径更新嵌套目录内的文件。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文件名或相对路径，例如 weekly-report/custom/output.md"
                    },
                    "content": {
                        "type": "string",
                        "description": "新的文件内容"
                    },
                    "subdir": {
                        "type": "string",
                        "default": "",
                        "description": "子目录（可选，支持任意相对路径），默认为空"
                    }
                },
                "required": ["filename", "content"]
            }
        },
        {
            "name": "sandbox_delete_file",
            "description": "删除对话沙箱中的文件。支持删除嵌套目录内的文件。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文件名或相对路径，例如 weekly-report/archive/old.md 或 reports/weekly.md"
                    },
                    "subdir": {
                        "type": "string",
                        "default": "",
                        "description": "子目录（可选，支持任意相对路径），默认为空"
                    }
                },
                "required": ["filename"]
            }
        },
        {
            "name": "sandbox_list_files",
            "description": "递归列出对话沙箱中的所有文件，适合先发现技能目录下的模板、参考文档和脚本。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "subdir": {
                        "type": "string",
                        "description": "可选，指定要遍历的相对目录。不指定则列出整个沙箱"
                    }
                }
            }
        },
        {
            "name": "sandbox_get_size",
            "description": "获取对话沙箱的总大小。",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        }
    ]
}


class SandboxFileHandler:
    """沙箱文件操作 MCP 工具处理器"""

    def __init__(self, db: Session | None = None):
        self.file_manager = SandboxFileManager()
        self.db = db

    @staticmethod
    def _normalize_rel_path(filename: str, subdir: str | None = "") -> str:
        parts = []
        if subdir:
            parts.append(str(subdir).strip().replace("\\", "/").strip("/"))
        parts.append(str(filename or "").strip().replace("\\", "/").strip("/"))
        return "/".join([item for item in parts if item and item != "."])

    @staticmethod
    def _sanitize_rel_path(value: str) -> str:
        normalized = (value or "").replace("\\", "/").strip("/")
        items = [item for item in normalized.split("/") if item not in {"", ".", ".."}]
        return "/".join(items)

    @staticmethod
    def _safe_filename(value: str, fallback: str) -> str:
        candidate = os.path.basename((value or "").replace("\\", "/")).strip()
        if not candidate:
            candidate = fallback
        candidate = re.sub(r"[<>:\"|?*\x00-\x1f]", "_", candidate).strip(" .")
        return candidate or fallback

    @staticmethod
    def _decode_sandbox_file_id(reference_file_id: int) -> int | None:
        try:
            value = int(reference_file_id)
        except Exception:
            return None
        if value >= SANDBOX_FILE_ID_OFFSET:
            return value - SANDBOX_FILE_ID_OFFSET
        return None

    @classmethod
    def _virtual_asset_path(cls, asset: Asset) -> str:
        scope_type = (asset.scope_type or "ASSET").upper()
        scope_id = int(asset.scope_id or 0)
        node_code = cls._sanitize_rel_path(asset.node_code or "_") or "_"
        file_name = asset.title or os.path.basename(asset.file_ref or "") or f"asset-{asset.id}.md"
        if "." not in file_name:
            file_name = f"{file_name}.md"
        safe_name = cls._safe_filename(file_name, f"asset-{asset.id}.md")
        return f"references/ASSET/{scope_type}/{scope_id}/{node_code}/{safe_name}"

    @classmethod
    def _virtual_uploaded_file_path(cls, file_item: UploadedFile) -> str:
        sandbox_rel = cls._sanitize_rel_path(
            file_item.sandbox_path or file_item.original_name or f"file-{file_item.id}.txt"
        )
        if not sandbox_rel:
            sandbox_rel = cls._safe_filename(
                file_item.original_name or "", f"file-{file_item.id}.txt"
            )
        return f"references/CONVERSATION/{int(file_item.conversation_id or 0)}/{sandbox_rel}"

    @staticmethod
    def _load_text_from_source(path_like: str | None, fallback: str) -> tuple[str, int]:
        candidate = Path(path_like or "")
        source_path = candidate if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
        if source_path.exists() and source_path.is_file():
            try:
                content = source_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = source_path.read_text(encoding="utf-8", errors="ignore")
            return content, source_path.stat().st_size
        content = fallback or ""
        return content, len(content.encode("utf-8"))

    def _build_virtual_reference_files(self, conversation_id: int) -> list[dict]:
        if self.db is None:
            return []
        state = (
            self.db.query(ConversationReferenceState)
            .filter(ConversationReferenceState.conversation_id == conversation_id)
            .first()
        )
        if not state or state.empty_mode == "sticky":
            return []

        selected_ids = sorted(
            {
                int(file_id)
                for file_id in (state.selected_file_ids or [])
                if str(file_id).isdigit() and int(file_id) > 0
            }
        )
        if not selected_ids:
            return []

        asset_ids = [file_id for file_id in selected_ids if self._decode_sandbox_file_id(file_id) is None]
        sandbox_file_ids = [
            decoded
            for decoded in (self._decode_sandbox_file_id(file_id) for file_id in selected_ids)
            if decoded is not None
        ]
        asset_map = {
            asset.id: asset
            for asset in (self.db.query(Asset).filter(Asset.id.in_(asset_ids)).all() if asset_ids else [])
        }
        sandbox_map = {
            item.id: item
            for item in (
                self.db.query(UploadedFile).filter(UploadedFile.id.in_(sandbox_file_ids)).all()
                if sandbox_file_ids
                else []
            )
        }

        virtual_files: list[dict] = []
        for selected_id in selected_ids:
            decoded = self._decode_sandbox_file_id(selected_id)
            if decoded is None:
                asset = asset_map.get(selected_id)
                if not asset:
                    continue
                virtual_path = self._virtual_asset_path(asset)
                content, size = self._load_text_from_source(
                    asset.file_ref, (asset.snapshot_markdown or asset.content or "")
                )
                virtual_files.append(
                    {
                        "file_id": selected_id,
                        "virtual_path": virtual_path,
                        "aliases": {virtual_path},
                        "filename": os.path.basename(virtual_path),
                        "content": content,
                        "size": size,
                        "modified_at": asset.updated_at.timestamp() if asset.updated_at else 0.0,
                        "source_kind": "ASSET",
                    }
                )
                continue

            file_item = sandbox_map.get(decoded)
            if not file_item:
                continue
            virtual_path = self._virtual_uploaded_file_path(file_item)
            logical_alias = f"CONVERSATION/{int(file_item.conversation_id or 0)}/{self._sanitize_rel_path(file_item.sandbox_path or file_item.original_name or '')}"
            content, size = self._load_text_from_source(
                file_item.stored_path, file_item.extracted_text or ""
            )
            aliases = {virtual_path}
            if logical_alias.endswith("/") is False and logical_alias != f"CONVERSATION/{int(file_item.conversation_id or 0)}/":
                aliases.add(logical_alias)
            virtual_files.append(
                {
                    "file_id": selected_id,
                    "virtual_path": virtual_path,
                    "aliases": aliases,
                    "filename": os.path.basename(virtual_path),
                    "content": content,
                    "size": size,
                    "modified_at": file_item.created_at.timestamp() if file_item.created_at else 0.0,
                    "source_kind": "SANDBOX_FILE",
                }
            )
        return virtual_files

    def handle_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        conversation_id: int
    ) -> dict:
        """
        处理沙箱文件操作工具调用

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            conversation_id: 对话 ID

        Returns:
            {
                "success": bool,
                "content": str,
                "error": Optional[str]
            }
        """
        try:
            if tool_name == "sandbox_create_file":
                return self._handle_create_file(arguments, conversation_id)
            elif tool_name == "sandbox_read_file":
                return self._handle_read_file(arguments, conversation_id)
            elif tool_name == "sandbox_update_file":
                return self._handle_update_file(arguments, conversation_id)
            elif tool_name == "sandbox_delete_file":
                return self._handle_delete_file(arguments, conversation_id)
            elif tool_name == "sandbox_list_files":
                return self._handle_list_files(arguments, conversation_id)
            elif tool_name == "sandbox_get_size":
                return self._handle_get_size(arguments, conversation_id)
            else:
                return {
                    "success": False,
                    "content": "",
                    "error": f"未知工具: {tool_name}"
                }

        except Exception as e:
            logger.error(f"处理工具调用失败: {tool_name}, {e}", exc_info=True)
            return {
                "success": False,
                "content": "",
                "error": f"工具调用失败: {str(e)}"
            }

    def _bump_unread_change_count(self, conversation_id: int, delta: int = 1) -> None:
        if self.db is None or delta <= 0:
            return
        try:
            increase_sandbox_unread_change_count(self.db, conversation_id, delta=delta)
        except Exception:
            logger.debug(
                "累加沙箱未读变更计数失败: conversation_id=%s, delta=%s",
                conversation_id,
                delta,
                exc_info=True,
            )

    def _handle_create_file(self, arguments: dict, conversation_id: int) -> dict:
        """处理创建文件工具调用"""
        filename = arguments.get("filename")
        content = arguments.get("content", "")
        subdir = arguments.get("subdir", "")

        if not filename:
            return {
                "success": False,
                "content": "",
                "error": "缺少必需参数: filename"
            }

        result = self.file_manager.create_file(conversation_id, filename, content, subdir)

        if result["success"]:
            self._bump_unread_change_count(conversation_id, delta=1)
            return {
                "success": True,
                "content": json.dumps({
                    "status": "success",
                    "message": result["message"],
                    "path": result["path"],
                    "size": result["size"]
                }, ensure_ascii=False),
                "error": None
            }
        else:
            return {
                "success": False,
                "content": "",
                "error": result["message"]
            }

    def _handle_read_file(self, arguments: dict, conversation_id: int) -> dict:
        """处理读取文件工具调用"""
        filename = arguments.get("filename")
        subdir = arguments.get("subdir", "")

        if not filename:
            return {
                "success": False,
                "content": "",
                "error": "缺少必需参数: filename"
            }

        result = self.file_manager.read_file(conversation_id, filename, subdir)
        if not result["success"]:
            virtual_files = self._build_virtual_reference_files(conversation_id)
            requested_path = self._normalize_rel_path(filename, subdir)
            absolute_match = re.search(r"/sandbox/\d+/(.*)$", requested_path)
            if absolute_match:
                requested_path = self._sanitize_rel_path(absolute_match.group(1))
            match = next(
                (
                    item
                    for item in virtual_files
                    if requested_path in item["aliases"] or requested_path == item["virtual_path"]
                ),
                None,
            )
            if match is None and requested_path:
                basename = os.path.basename(requested_path)
                candidates = [
                    item for item in virtual_files if os.path.basename(item["virtual_path"]) == basename
                ]
                if len(candidates) == 1:
                    match = candidates[0]
            if match is not None:
                result = {
                    "success": True,
                    "message": "文件读取成功（引用虚拟路径）",
                    "content": match["content"],
                    "size": int(match["size"] or 0),
                    "resolved_path": match["virtual_path"],
                }

        if result["success"]:
            return {
                "success": True,
                "content": json.dumps({
                    "status": "success",
                    "message": result["message"],
                    "filename": filename,
                    "resolved_path": result.get("resolved_path"),
                    "content": result["content"],
                    "size": result["size"]
                }, ensure_ascii=False),
                "error": None
            }
        else:
            return {
                "success": False,
                "content": "",
                "error": result["message"]
            }

    def _handle_update_file(self, arguments: dict, conversation_id: int) -> dict:
        """处理更新文件工具调用"""
        filename = arguments.get("filename")
        content = arguments.get("content", "")
        subdir = arguments.get("subdir", "")

        if not filename:
            return {
                "success": False,
                "content": "",
                "error": "缺少必需参数: filename"
            }

        result = self.file_manager.update_file(conversation_id, filename, content, subdir)

        if result["success"]:
            self._bump_unread_change_count(conversation_id, delta=1)
            return {
                "success": True,
                "content": json.dumps({
                    "status": "success",
                    "message": result["message"],
                    "size": result["size"]
                }, ensure_ascii=False),
                "error": None
            }
        else:
            return {
                "success": False,
                "content": "",
                "error": result["message"]
            }

    def _handle_delete_file(self, arguments: dict, conversation_id: int) -> dict:
        """处理删除文件工具调用"""
        filename = arguments.get("filename")
        subdir = arguments.get("subdir", "")

        if not filename:
            return {
                "success": False,
                "content": "",
                "error": "缺少必需参数: filename"
            }

        result = self.file_manager.delete_file(conversation_id, filename, subdir)

        if result["success"]:
            self._bump_unread_change_count(conversation_id, delta=1)
            return {
                "success": True,
                "content": json.dumps({
                    "status": "success",
                    "message": result["message"]
                }, ensure_ascii=False),
                "error": None
            }
        else:
            return {
                "success": False,
                "content": "",
                "error": result["message"]
            }

    def _handle_list_files(self, arguments: dict, conversation_id: int) -> dict:
        """处理列出文件工具调用"""
        subdir = arguments.get("subdir")

        result = self.file_manager.list_files(conversation_id, subdir)
        if result["success"]:
            virtual_files = self._build_virtual_reference_files(conversation_id)
            normalized_subdir = self._sanitize_rel_path(str(subdir or ""))
            existing_paths = {
                str(item.get("sandbox_path") or "").replace("\\", "/")
                for item in result["files"]
            }
            for item in virtual_files:
                virtual_path = item["virtual_path"]
                if normalized_subdir and not (
                    virtual_path == normalized_subdir
                    or virtual_path.startswith(f"{normalized_subdir}/")
                ):
                    continue
                if virtual_path in existing_paths:
                    continue
                rel_path = (
                    virtual_path[len(normalized_subdir) + 1 :]
                    if normalized_subdir and virtual_path.startswith(f"{normalized_subdir}/")
                    else virtual_path
                )
                result["files"].append(
                    {
                        "filename": item["filename"],
                        "relative_path": rel_path,
                        "sandbox_path": virtual_path,
                        "subdir": virtual_path.split("/", 1)[0],
                        "size": int(item["size"] or 0),
                        "modified_at": float(item["modified_at"] or 0.0),
                    }
                )
                result["total_size"] += int(item["size"] or 0)
            result["files"].sort(key=lambda x: x.get("modified_at", 0), reverse=True)
            result["message"] = f"找到 {len(result['files'])} 个文件"

        if result["success"]:
            return {
                "success": True,
                "content": json.dumps({
                    "status": "success",
                    "message": result["message"],
                    "files": result["files"],
                    "total_size": result["total_size"],
                    "count": len(result["files"])
                }, ensure_ascii=False, indent=2),
                "error": None
            }
        else:
            return {
                "success": False,
                "content": "",
                "error": result["message"]
            }

    def _handle_get_size(self, arguments: dict, conversation_id: int) -> dict:
        """处理获取沙箱大小工具调用"""
        size = self.file_manager.get_sandbox_size(conversation_id)
        size_mb = size / 1024 / 1024

        return {
            "success": True,
            "content": json.dumps({
                "status": "success",
                "size_bytes": size,
                "size_mb": round(size_mb, 2),
                "message": f"沙箱大小: {size_mb:.2f}MB / {DEFAULT_SANDBOX_SIZE_LIMIT / 1024 / 1024:.0f}MB"
            }, ensure_ascii=False),
            "error": None
        }


def get_sandbox_tools() -> list[dict]:
    """获取沙箱文件操作工具定义（OpenAI Function Calling 格式）"""
    tools = []

    for tool_def in SANDBOX_TOOLS_DEFINITION["tools"]:
        tool = {
            "type": "function",
            "function": {
                "name": tool_def["name"],
                "description": tool_def["description"],
                "parameters": tool_def["inputSchema"]
            }
        }
        tools.append(tool)

    return tools


def get_sandbox_tool_names() -> list[str]:
    """获取沙箱文件操作工具名称列表"""
    return [tool["name"] for tool in SANDBOX_TOOLS_DEFINITION["tools"]]


# 导出默认限制
DEFAULT_SANDBOX_SIZE_LIMIT = 100 * 1024 * 1024  # 100MB
