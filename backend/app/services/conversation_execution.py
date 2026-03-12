import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from collections.abc import AsyncIterator
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.conversation import Conversation
from app.models.mcp import Mcp
from app.models.mcp_call_log import McpCallLog
from app.models.message import Message, MessageToolCall
from app.models.uploaded_file import UploadedFile
from app.services.mcp.circuit_breaker import get_circuit_breaker_registry
from app.services.mcp.client_manager import MCPClientManager
from app.services.mcp.tool_executor import ToolExecutor
from app.services.mcp_service import get_decrypted_config
from app.services.conversation_events import get_conversation_event_bus
from app.services.sandbox_file_manager import SandboxFileManager
from app.services.audit_service import AuditContext, AuditEventCollector
from app.services.conversation_sidebar_signal import (
    SIDEBAR_SIGNAL_CANCELLED,
    SIDEBAR_SIGNAL_ERROR,
    SIDEBAR_SIGNAL_RUNNING,
    SIDEBAR_SIGNAL_WAITING_SKILL_CONFIRMATION,
    apply_sidebar_signal,
)
from app.services.sandbox_change_counter import increase_sandbox_unread_change_count
from app.utils.file_detector import detect_files
from app.utils.token_counter import count_tokens


class ConversationExecutionEngine:
    """统一的会话执行内核：处理流式输出 + tool call 循环。"""

    LIVE_PERSIST_INTERVAL_SECONDS = 0.35
    SANDBOX_OUTPUT_DIR_KEYS = {
        "output_dir",
        "outputDir",
        "output_path",
        "outputPath",
        "save_dir",
        "saveDir",
        "download_dir",
        "downloadDir",
        "target_dir",
        "targetDir",
        "directory",
        "dir",
        "output_directory",
        "outputDirectory",
    }
    SANDBOX_WORKDIR_KEYS = {"cwd", "workdir", "work_dir", "workspace", "working_directory"}
    SANDBOX_FILE_PATH_KEYS = {"filePath", "file_path", "filepath", "localPath", "local_path"}

    def __init__(self, db: Session, user_id: int, tool_executor: ToolExecutor):
        self.db = db
        self.user_id = user_id
        self.tool_executor = tool_executor
        self.settings = get_settings()

    def _get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        try:
            return (
                self.db.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
        except Exception:
            return None

    def set_live_status(
        self,
        conversation_id: int,
        *,
        status: str,
        message_id: Optional[int] = None,
        error_message: Optional[str] = None,
        stage: Optional[str] = None,
        stage_detail: Optional[str] = None,
        stage_meta: Optional[dict[str, Any]] = None,
        round_no: Optional[int] = None,
        sidebar_signal_state: Optional[str] = None,
        commit: bool = True,
    ) -> None:
        conv = self._get_conversation(conversation_id)
        if not conv:
            return
        now = datetime.now()
        if stage is None:
            if status == "running":
                stage = "preparing"
                stage_detail = stage_detail or "准备中：正在组装上下文与执行环境"
                stage_meta = stage_meta or {"phase": "preparing"}
            elif status == "waiting_skill_confirmation":
                stage = "waiting_skill_confirmation"
                stage_detail = stage_detail or "等待确认：请确认是否激活技能"
                stage_meta = stage_meta or {"phase": "waiting_skill_confirmation"}
            elif status == "cancelled":
                stage = "cancelled"
                stage_detail = stage_detail or "已取消：本轮任务已停止"
                stage_meta = stage_meta or {"phase": "cancelled"}
            elif status == "error":
                stage = "error"
                stage_detail = stage_detail or f"执行异常：{error_message or '本轮任务失败'}"
                stage_meta = stage_meta or {"phase": "error"}
        conv.live_status = status
        if message_id is not None:
            conv.live_message_id = message_id
            self._ensure_live_message_active(conversation_id, message_id)
        elif status == "idle":
            conv.live_message_id = None
        conv.live_error_message = error_message
        if stage is not None:
            conv.live_stage = stage
        if stage_detail is not None:
            conv.live_stage_detail = stage_detail
        if stage_meta is not None:
            conv.live_stage_meta_json = json.dumps(stage_meta, ensure_ascii=False)
        elif stage is not None:
            conv.live_stage_meta_json = None
        if round_no is not None:
            conv.live_round_no = int(round_no)
        if status in {"idle", "cancelled", "error"} and stage is None:
            conv.live_stage = None
            conv.live_stage_detail = None
            conv.live_stage_meta_json = None
            conv.live_round_no = None
        if status == "running":
            if conv.live_started_at is None:
                conv.live_started_at = now
            conv.live_updated_at = now
        elif status == "idle":
            conv.live_started_at = None
            conv.live_updated_at = now
        else:
            conv.live_updated_at = now

        signal_state = sidebar_signal_state
        if signal_state is None:
            if status == "running":
                signal_state = SIDEBAR_SIGNAL_RUNNING
            elif status == "waiting_skill_confirmation":
                signal_state = SIDEBAR_SIGNAL_WAITING_SKILL_CONFIRMATION
            elif status == "error":
                signal_state = SIDEBAR_SIGNAL_ERROR
            elif status == "cancelled":
                signal_state = SIDEBAR_SIGNAL_CANCELLED
        if signal_state:
            apply_sidebar_signal(conv, state=signal_state, event_time=now)
        if commit:
            self.db.commit()
            self.db.refresh(conv)
            get_conversation_event_bus().publish_conversation_snapshot_nowait(
                conv=conv,
                event_type="conversation.live_state_changed",
            )

    def _ensure_live_message_active(self, conversation_id: int, message_id: int) -> None:
        """确保 live_message_id 指向的消息对会话详情可见。"""
        target = (
            self.db.query(Message)
            .filter(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
            )
            .first()
        )
        if not target or target.is_active:
            return
        target.is_active = True

    def _touch_live_state(
        self, conversation_id: int, message_id: Optional[int] = None, *, commit: bool = True
    ) -> None:
        conv = self._get_conversation(conversation_id)
        if not conv:
            return
        conv.live_status = "running"
        if message_id is not None:
            conv.live_message_id = message_id
        if conv.live_started_at is None:
            conv.live_started_at = datetime.now()
        conv.live_updated_at = datetime.now()
        conv.live_error_message = None
        if commit:
            self.db.commit()

    def _persist_live_round_message(
        self,
        *,
        conversation_id: int,
        assistant_msg: Message,
        content: str,
        reasoning_content: str,
        force: bool,
        state: dict[str, Any],
    ) -> None:
        now = time.monotonic()
        if not force and now - state["last_persist_at"] < self.LIVE_PERSIST_INTERVAL_SECONDS:
            return
        assistant_msg.content = content
        assistant_msg.reasoning_content = reasoning_content or None
        self._touch_live_state(conversation_id, assistant_msg.id, commit=False)
        self.db.commit()
        self.db.refresh(assistant_msg)
        state["last_persist_at"] = now

    def build_mcp_config_cache(
        self, tool_routing: dict[str, dict[str, Any]]
    ) -> dict[int, tuple[dict, str]]:
        mcp_config_cache: dict[int, tuple[dict, str]] = {}
        for route_info in tool_routing.values():
            mid = route_info["mcp_id"]
            if mid in mcp_config_cache:
                continue
            mcp_obj = self.db.query(Mcp).filter(Mcp.id == mid).first()
            if not mcp_obj:
                continue
            cfg = get_decrypted_config(mcp_obj)
            mcp_config_cache[mid] = (cfg, MCPClientManager.detect_transport_type(cfg))
        return mcp_config_cache

    @staticmethod
    def _rewrite_tool_result_paths(
        content: str, path_mapping: dict[str, str]
    ) -> str:
        """将工具结果中的本地绝对路径重写为沙箱相对路径。"""
        if not content or not path_mapping:
            return content

        normalized_mapping: dict[str, str] = {}
        for src, dst in path_mapping.items():
            if not src or not dst:
                continue
            normalized_mapping[os.path.abspath(src)] = dst

        def _replace(value: Any) -> Any:
            if isinstance(value, str):
                abs_value = os.path.abspath(value) if value.startswith("/") else None
                if abs_value and abs_value in normalized_mapping:
                    return normalized_mapping[abs_value]
                return value
            if isinstance(value, dict):
                return {k: _replace(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_replace(item) for item in value]
            return value

        try:
            payload = json.loads(content)
            rewritten = _replace(payload)
            return json.dumps(rewritten, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            rewritten_text = content
            for src_abs, dst in normalized_mapping.items():
                rewritten_text = rewritten_text.replace(src_abs, dst)
            return rewritten_text

    @staticmethod
    def _extract_file_title_mapping(content: str) -> dict[str, str]:
        """
        从工具 JSON 返回中提取 `绝对文件路径 -> 标题` 映射。
        常见结构：{"data": {"filePath": "...", "title": "..."}}
        """
        if not content:
            return {}

        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {}

        mapping: dict[str, str] = {}

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                path_value: Optional[str] = None
                title_value: Optional[str] = None
                for key in ("filePath", "file_path", "filepath", "path"):
                    value = node.get(key)
                    if isinstance(value, str) and value.startswith("/"):
                        path_value = os.path.abspath(value)
                        break
                for key in ("title", "fileName", "filename", "name"):
                    value = node.get(key)
                    if isinstance(value, str) and value.strip():
                        title_value = value.strip()
                        break
                if path_value and title_value:
                    mapping[path_value] = title_value
                for value in node.values():
                    _walk(value)
                return
            if isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(payload)
        return mapping

    @staticmethod
    def _sanitize_generated_filename(title: str, fallback_filename: str) -> str:
        """
        用业务标题生成可落盘文件名。
        - 保留中文等业务字符
        - 去掉路径分隔与系统非法字符
        - 默认沿用原文件扩展名
        """
        default_name = fallback_filename or "generated_file"
        fallback_ext = os.path.splitext(default_name)[1]
        raw = (title or "").strip()
        if not raw:
            return default_name

        raw = raw.replace("/", "_").replace("\\", "_")
        raw = re.sub(r'[\x00-\x1f<>:"|?*]', "_", raw)
        raw = re.sub(r"\s+", " ", raw).strip(" .")
        if not raw:
            return default_name

        stem, ext = os.path.splitext(raw)
        if ext:
            return raw
        return f"{raw}{fallback_ext}" if fallback_ext else raw

    @staticmethod
    def _ensure_unique_generated_filename(
        filename: str,
        generated_dir: str,
        reserved_names: set[str],
    ) -> str:
        candidate = filename or "generated_file"
        stem, ext = os.path.splitext(candidate)
        index = 2
        while candidate in reserved_names or os.path.exists(os.path.join(generated_dir, candidate)):
            candidate = f"{stem} ({index}){ext}"
            index += 1
        reserved_names.add(candidate)
        return candidate

    def _cleanup_generated_source_file(self, source_path: str) -> None:
        """清理工具在后端本地工作目录产生的临时文件，避免越过会话沙箱边界。"""
        source_abs = os.path.abspath(source_path)
        upload_dir_abs = os.path.abspath(self.settings.UPLOAD_DIR)
        backend_root = os.path.dirname(upload_dir_abs)
        work_master_dir = os.path.abspath(os.path.join(backend_root, ".work-master"))
        sandbox_root_dir = os.path.abspath(os.path.join(upload_dir_abs, "sandbox"))
        try:
            in_backend_work_master = os.path.commonpath(
                [source_abs, work_master_dir]
            ) == work_master_dir
            in_sandbox_work_master = (
                os.path.commonpath([source_abs, sandbox_root_dir]) == sandbox_root_dir
                and "/.work-master/" in source_abs.replace("\\", "/")
            )
            if (
                os.path.exists(source_abs)
                and (in_backend_work_master or in_sandbox_work_master)
            ):
                os.remove(source_abs)
        except Exception:
            logger.debug("清理 MCP 源文件失败: %s", source_abs, exc_info=True)

    @staticmethod
    def _collect_files_under_dir(root_dir: str) -> list[str]:
        if not root_dir or not os.path.isdir(root_dir):
            return []
        paths: list[str] = []
        for root, _, files in os.walk(root_dir):
            for name in files:
                paths.append(os.path.join(root, name))
        return paths

    def _inject_sandbox_generation_args(
        self,
        *,
        args_dict: dict[str, Any],
        route_info: Optional[dict[str, Any]],
        conversation_id: int,
    ) -> dict[str, Any]:
        """
        当工具 schema 声明支持输出目录/工作目录参数时，注入当前对话沙箱目录。
        """
        if not isinstance(args_dict, dict) or not route_info:
            return args_dict
        input_schema = route_info.get("input_schema") or {}
        if not isinstance(input_schema, dict):
            return args_dict
        properties = input_schema.get("properties") or {}
        if not isinstance(properties, dict) or not properties:
            return args_dict

        sandbox_manager = SandboxFileManager(self.settings)
        sandbox_manager.init_sandbox(conversation_id)
        sandbox_root = sandbox_manager.get_sandbox_path(conversation_id)
        generated_dir = os.path.join(sandbox_root, "generated")
        os.makedirs(generated_dir, exist_ok=True)

        merged_args = dict(args_dict)
        for key in properties.keys():
            if key in self.SANDBOX_OUTPUT_DIR_KEYS and not merged_args.get(key):
                merged_args[key] = generated_dir
            elif key in self.SANDBOX_WORKDIR_KEYS and not merged_args.get(key):
                merged_args[key] = sandbox_root
        return merged_args

    def _rewrite_relative_file_paths_for_sandbox(
        self,
        *,
        args_dict: dict[str, Any],
        route_info: Optional[dict[str, Any]],
        conversation_id: int,
    ) -> dict[str, Any]:
        """
        快速兜底：将 upload_to_yuque 的相对 filePath 改写为当前会话沙箱绝对路径。
        """
        if not isinstance(args_dict, dict) or not route_info:
            return args_dict
        if route_info.get("tool_name") != "upload_to_yuque":
            return args_dict

        sandbox_manager = SandboxFileManager(self.settings)
        sandbox_manager.init_sandbox(conversation_id)
        sandbox_root = sandbox_manager.get_sandbox_path(conversation_id)

        rewritten = dict(args_dict)
        for key in self.SANDBOX_FILE_PATH_KEYS:
            value = rewritten.get(key)
            if not isinstance(value, str):
                continue
            candidate = value.strip()
            if not candidate:
                continue
            if candidate.startswith(("http://", "https://")):
                continue
            if os.path.isabs(candidate):
                continue

            normalized = candidate.replace("\\", "/").strip()
            while normalized.startswith("./"):
                normalized = normalized[2:]
            normalized = normalized.lstrip("/")
            if not normalized:
                continue

            abs_candidate = os.path.abspath(os.path.join(sandbox_root, normalized))
            if os.path.isfile(abs_candidate):
                rewritten[key] = abs_candidate

        return rewritten

    async def _execute_tool_call(
        self,
        tc: dict[str, Any],
        route_info: Optional[dict[str, Any]],
        mcp_config_cache: dict[int, tuple[dict, str]],
        conversation_id: int,
        assistant_msg_id: Optional[int],
        persist_logs: bool = True,
        persist_generated_files: bool = True,
    ) -> dict[str, Any]:
        prefixed_name = tc["function"]["name"]
        arguments_str = tc["function"]["arguments"]

        # 处理 Skill 激活工具（特殊处理，不需要 route_info）
        if prefixed_name.startswith("activate_skill_"):
            print(
                f"[SkillActivation] Detected skill activation tool call: {prefixed_name}"
            )
            from app.services.skill_activation_manager import SkillActivationManager

            skill_id = SkillActivationManager.parse_activation_tool_call(prefixed_name)
            print(f"[SkillActivation] Parsed skill_id: {skill_id}")
            if skill_id:
                skill_name = None
                skill_desc = ""
                active_skills = SkillActivationManager.get_active_skills(
                    conversation_id, self.db, self.user_id
                )
                for active_skill in active_skills:
                    if int(active_skill.get("id", -1)) != skill_id:
                        continue
                    active_name = active_skill.get("name") or f"Skill (id={skill_id})"
                    return {
                        "content": json.dumps(
                            {
                                "type": "skill_already_active",
                                "success": True,
                                "skill_id": skill_id,
                                "skill_name": active_name,
                                "message": (
                                    f"Skill「{active_name}」已激活，无需重复确认。"
                                    "请直接继续当前请求。"
                                ),
                            },
                            ensure_ascii=False,
                        ),
                        "error": None,
                        "_success": True,
                        "files": [],
                    }

                # 获取 Skill 信息
                from app.models.skill import Skill, SkillVersion

                skill = self.db.query(Skill).filter(Skill.id == skill_id).first()
                if skill:
                    skill_name = skill.name
                    # 读取技能当前发布版本的 brief_desc
                    skill_version = None
                    if skill.published_version_id:
                        skill_version = (
                            self.db.query(SkillVersion)
                            .filter(SkillVersion.id == skill.published_version_id)
                            .first()
                        )
                    skill_desc = (
                        skill_version.brief_desc
                        if skill_version
                        else (skill.description or "")
                    )

                # 返回 Skill 激活请求信息（需要前端确认）
                return {
                    "content": json.dumps(
                        {
                            "type": "skill_activation_request",
                            "skill_id": skill_id,
                            "skill_name": skill_name,
                            "skill_description": skill_desc,
                        },
                        ensure_ascii=False,
                    ),
                    "error": None,
                    "_success": True,
                    "_skill_activation": {
                        "skill_id": skill_id,
                        "skill_name": skill_name,
                        "skill_description": skill_desc,
                    },
                    "files": [],
                }

        # 处理沙箱文件操作工具（特殊处理，不需要 route_info）
        from app.mcp.handlers.sandbox_file_handler import (
            SandboxFileHandler,
            get_sandbox_tool_names,
        )

        if prefixed_name in get_sandbox_tool_names():
            try:
                args_dict = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                args_dict = {}

            handler = SandboxFileHandler(db=self.db)
            result = handler.handle_tool_call(prefixed_name, args_dict, conversation_id)

            if result["success"]:
                return {
                    "content": result["content"],
                    "error": None,
                    "_success": True,
                    "_sandbox_file": True,
                    "files": [],
                }
            else:
                return {
                    "content": json.dumps(
                        {"error": True, "message": result["error"]}, ensure_ascii=False
                    ),
                    "error": result["error"],
                    "_success": False,
                    "files": [],
                }

        if not route_info:
            return {
                "content": json.dumps(
                    {"error": True, "message": f"未知工具: {prefixed_name}"},
                    ensure_ascii=False,
                ),
                "error": f"未知工具: {prefixed_name}",
                "_success": False,
                "files": [],
            }

        try:
            args_dict = json.loads(arguments_str) if arguments_str else {}
        except json.JSONDecodeError:
            args_dict = {}
        args_dict = self._inject_sandbox_generation_args(
            args_dict=args_dict,
            route_info=route_info,
            conversation_id=conversation_id,
        )
        args_dict = self._rewrite_relative_file_paths_for_sandbox(
            args_dict=args_dict,
            route_info=route_info,
            conversation_id=conversation_id,
        )

        cached = mcp_config_cache.get(route_info["mcp_id"])
        if not cached:
            return {
                "content": json.dumps(
                    {"error": True, "message": "MCP 配置不可用"}, ensure_ascii=False
                ),
                "error": "MCP 配置不可用",
                "_success": False,
                "files": [],
            }

        config, t_type = cached
        result = await self.tool_executor.execute(
            mcp_id=route_info["mcp_id"],
            config_json=config,
            transport_type=t_type,
            tool_name=route_info["tool_name"],
            arguments=args_dict,
            timeout_seconds=route_info["timeout_seconds"],
            max_retries=route_info["max_retries"],
            circuit_breaker_threshold=route_info.get("circuit_breaker_threshold", 5),
            circuit_breaker_recovery=route_info.get("circuit_breaker_recovery", 300),
        )

        if persist_logs:
            breaker = get_circuit_breaker_registry().get_or_create(route_info["mcp_id"])
            mcp_record = (
                self.db.query(Mcp).filter(Mcp.id == route_info["mcp_id"]).first()
            )
            if mcp_record:
                mcp_record.health_status = breaker.health_status
                mcp_record.consecutive_failures = breaker._failure_count
                mcp_record.circuit_open_until = breaker._open_until

            call_log = McpCallLog(
                user_id=self.user_id,
                conversation_id=conversation_id,
                message_id=assistant_msg_id,
                mcp_id=route_info["mcp_id"],
                tool_name=route_info["tool_name"],
                tool_call_id=tc["id"],
                arguments=arguments_str,
                result=result.content[:16384] if result.content else None,
                is_success=result.success,
                error_message=result.error,
                response_time_ms=result.response_time_ms,
            )
            self.db.add(call_log)

        if not result.success:
            return {
                "content": json.dumps(
                    {"error": True, "message": result.error}, ensure_ascii=False
                ),
                "error": result.error,
                "_success": False,
                "files": [],
            }

        saved_files: list[dict[str, Any]] = []
        path_mapping: dict[str, str] = {}
        if persist_generated_files:
            sandbox_manager = SandboxFileManager(self.settings)
            sandbox_manager.init_sandbox(conversation_id)
            sandbox_root = sandbox_manager.get_sandbox_path(conversation_id)
            generated_dir = os.path.join(sandbox_root, "generated")
            os.makedirs(generated_dir, exist_ok=True)

            detected_files = detect_files(result.content)
            sandbox_work_master_dir = os.path.join(sandbox_root, ".work-master")
            if os.path.isdir(sandbox_work_master_dir):
                detected_files.extend(self._collect_files_under_dir(sandbox_work_master_dir))

            if detected_files:
                # 去重并保持顺序，避免多次处理同一路径
                normalized_detected: list[str] = []
                seen_paths: set[str] = set()
                for file_path in detected_files:
                    abs_file_path = os.path.abspath(file_path)
                    if abs_file_path in seen_paths:
                        continue
                    seen_paths.add(abs_file_path)
                    normalized_detected.append(abs_file_path)

                reserved_names: set[str] = set()
                file_title_mapping = self._extract_file_title_mapping(result.content)
                for abs_file_path in normalized_detected:
                    fallback_filename = os.path.basename(abs_file_path)
                    filename = self._sanitize_generated_filename(
                        file_title_mapping.get(abs_file_path, ""),
                        fallback_filename=fallback_filename,
                    )
                    filename = self._ensure_unique_generated_filename(
                        filename=filename,
                        generated_dir=generated_dir,
                        reserved_names=reserved_names,
                    )
                    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                    try:
                        with open(abs_file_path, "rb") as f:
                            file_bytes = f.read()
                        sandbox_result = sandbox_manager.create_file_binary(
                            conversation_id=conversation_id,
                            filename=filename,
                            content=file_bytes,
                            subdir="generated",
                            overwrite=False,
                        )
                        if not sandbox_result["success"]:
                            continue
                        stored_path = sandbox_result["path"]
                        sandbox_relative_path = os.path.join(
                            "generated", filename
                        ).replace("\\", "/")
                        path_mapping[abs_file_path] = sandbox_relative_path
                        self._cleanup_generated_source_file(abs_file_path)
                        if persist_logs and assistant_msg_id:
                            uploaded = UploadedFile(
                                conversation_id=conversation_id,
                                user_id=self.user_id,
                                message_id=assistant_msg_id,
                                source="generated",
                                original_name=filename,
                                stored_path=stored_path,
                                sandbox_path=sandbox_relative_path,
                                file_size=os.path.getsize(stored_path),
                                file_type=ext,
                            )
                            self.db.add(uploaded)
                            self.db.flush()
                            saved_files.append(
                                {
                                    "file_id": uploaded.id,
                                    "filename": uploaded.original_name,
                                    "file_size": uploaded.file_size,
                                }
                            )
                    except Exception:
                        continue

            # 清理空的 .work-master 目录，避免在沙箱面板产生误导
            try:
                if os.path.isdir(sandbox_work_master_dir) and not os.listdir(
                    sandbox_work_master_dir
                ):
                    os.rmdir(sandbox_work_master_dir)
            except Exception:
                logger.debug(
                    "清理沙箱内空 .work-master 目录失败: %s",
                    sandbox_work_master_dir,
                    exc_info=True,
                )

        if saved_files:
            increase_sandbox_unread_change_count(
                self.db,
                conversation_id,
                delta=len(saved_files),
            )

        sanitized_content = self._rewrite_tool_result_paths(result.content, path_mapping)
        return {"content": sanitized_content, "_success": True, "files": saved_files}

    async def run_agent_loop(
        self,
        *,
        provider: Any,
        context: list[dict[str, Any]],
        model_name: str,
        tools_param: Optional[list[dict[str, Any]]],
        tool_routing: dict[str, dict[str, Any]],
        mcp_config_cache: dict[int, tuple[dict, str]],
        conversation_id: int,
        parent_message_id: int,
        final_branch_index: int = 0,
        is_active: bool = True,
        max_tool_rounds: int = 10,
        persist_logs: bool = True,
        persist_generated_files: bool = False,
        on_event: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
        audit_context: Optional[AuditContext] = None,
        stream_call: Optional[
            Callable[
                [list[dict[str, Any]], str, Optional[list[dict[str, Any]]]],
                AsyncIterator[dict[str, Any]],
            ]
        ] = None,
    ) -> dict[str, Any]:
        tool_round = 0
        total_output = 0
        last_msg_parent_id = parent_message_id
        audit_collector: Optional[AuditEventCollector] = None
        current_audit_ctx = audit_context
        if persist_logs:
            audit_collector = AuditEventCollector(self.db)
            if current_audit_ctx is None:
                current_audit_ctx = audit_collector.init_trace(
                    conversation_id=conversation_id,
                    user_id=self.user_id,
                    round_no=self._infer_round_no(conversation_id, parent_message_id),
                )
        # 同一用户轮次内，禁止重复触发同一个技能激活工具
        attempted_activation_skill_ids: set[int] = set()

        while True:
            current_round_no = tool_round + 1
            self.set_live_status(
                conversation_id,
                status="running",
                stage="llm_streaming",
                stage_detail=f"模型生成中：第 {current_round_no} 轮推理",
                stage_meta={"phase": "llm_streaming"},
                round_no=current_round_no,
            )
            full_content = ""
            reasoning_content_buffer = ""
            tool_calls_buffer: list[dict[str, Any]] = []
            current_tools = tools_param if tool_round < max_tool_rounds else None
            branch_index = final_branch_index
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content="",
                token_count=0,
                model_name=model_name,
                reasoning_content=None,
                parent_id=last_msg_parent_id,
                branch_index=branch_index,
                is_active=is_active,
            )
            self.db.add(assistant_msg)
            self.db.flush()
            self._touch_live_state(conversation_id, assistant_msg.id)
            live_round_state = {"last_persist_at": 0.0}

            if stream_call is not None:
                stream = stream_call(context, model_name, current_tools)
            else:
                stream = provider.chat_completion_stream(
                    messages=context,
                    model=model_name,
                    temperature=0.7,
                    tools=current_tools,
                )

            if audit_collector and current_audit_ctx:
                audit_collector.append_event(
                    current_audit_ctx,
                    event_type="llm_request_raw",
                    source="backend",
                    payload={
                        "model": model_name,
                        "messages": context,
                        "temperature": 0.7,
                        "tools": current_tools,
                    },
                )

            try:
                saw_content_in_round = False
                async for event in stream:
                    if audit_collector and current_audit_ctx:
                        audit_collector.append_event(
                            current_audit_ctx,
                            event_type="llm_response_raw",
                            source="llm",
                            payload=event,
                        )

                    if event["type"] == "content_delta":
                        if not saw_content_in_round:
                            saw_content_in_round = True
                            self.set_live_status(
                                conversation_id,
                                status="running",
                                stage="llm_streaming",
                                stage_detail=f"模型生成中：第 {current_round_no} 轮推理",
                                stage_meta={"phase": "llm_streaming"},
                                round_no=current_round_no,
                            )
                        full_content += event["content"]
                        self._persist_live_round_message(
                            conversation_id=conversation_id,
                            assistant_msg=assistant_msg,
                            content=full_content,
                            reasoning_content=reasoning_content_buffer,
                            force=False,
                            state=live_round_state,
                        )
                        if on_event:
                            await on_event({"type": "chunk", "content": event["content"]})
                    elif event["type"] == "tool_call":
                        tool_calls_buffer.append(event["tool_call"])
                    elif event["type"] == "reasoning_content_delta":
                        reasoning_content_buffer += event["content"]
                        self._persist_live_round_message(
                            conversation_id=conversation_id,
                            assistant_msg=assistant_msg,
                            content=full_content,
                            reasoning_content=reasoning_content_buffer,
                            force=False,
                            state=live_round_state,
                        )
                        if on_event:
                            await on_event(
                                {"type": "thinking_delta", "content": event["content"]}
                            )
                    elif event["type"] == "reasoning_content_done":
                        if on_event:
                            await on_event({"type": "thinking_done"})
                    elif event["type"] == "fallback_triggered":
                        if audit_collector and current_audit_ctx:
                            audit_collector.append_event(
                                current_audit_ctx,
                                event_type="fallback_triggered",
                                source="system",
                                payload=event,
                            )
                        if on_event:
                            await on_event(event)
                    else:
                        if on_event:
                            await on_event(event)
            except Exception as exc:
                # LLM 流在首个 token 前中断时，可能只留下空 assistant 占位消息。
                # 这里主动清理，避免前端出现“空白 AI 气泡”。
                if not full_content and not reasoning_content_buffer and not tool_calls_buffer:
                    try:
                        self.db.delete(assistant_msg)
                        self.db.flush()
                    except Exception:
                        self.db.rollback()
                error_text = str(exc).lower()
                if "timeout" in error_text or "timed out" in error_text:
                    event_type = "request_timeout"
                elif "disconnect" in error_text or "cancel" in error_text:
                    event_type = "stream_interrupted"
                else:
                    event_type = "llm_error"
                if audit_collector and current_audit_ctx:
                    audit_collector.append_event(
                        current_audit_ctx,
                        event_type=event_type,
                        source="system",
                        payload={"error": str(exc)},
                        error_message=str(exc),
                    )
                    self.db.commit()
                raise

            if not tool_calls_buffer:
                output_tokens = count_tokens(full_content)
                total_output += output_tokens
                assistant_msg.content = full_content
                assistant_msg.token_count = output_tokens
                assistant_msg.model_name = model_name
                assistant_msg.reasoning_content = reasoning_content_buffer or None
                assistant_msg.parent_id = last_msg_parent_id
                assistant_msg.branch_index = final_branch_index
                assistant_msg.is_active = is_active
                self._persist_live_round_message(
                    conversation_id=conversation_id,
                    assistant_msg=assistant_msg,
                    content=full_content,
                    reasoning_content=reasoning_content_buffer,
                    force=True,
                    state=live_round_state,
                )
                self.db.commit()
                self.db.refresh(assistant_msg)
                if audit_collector and current_audit_ctx:
                    audit_collector.finish_trace(current_audit_ctx.trace_id)
                    self.db.commit()
                if on_event:
                    await on_event({"type": "done", "message_id": assistant_msg.id})
                return {
                    "message_id": assistant_msg.id,
                    "content": full_content,
                    "tool_rounds": tool_round,
                    "output_tokens": total_output,
                }

            tool_round += 1
            assistant_msg.content = full_content or ""
            assistant_msg.token_count = count_tokens(full_content)
            assistant_msg.model_name = model_name
            assistant_msg.reasoning_content = reasoning_content_buffer or None
            assistant_msg.parent_id = last_msg_parent_id
            assistant_msg.branch_index = 0
            assistant_msg.is_active = is_active
            self._persist_live_round_message(
                conversation_id=conversation_id,
                assistant_msg=assistant_msg,
                content=assistant_msg.content,
                reasoning_content=reasoning_content_buffer,
                force=True,
                state=live_round_state,
            )

            for tc in tool_calls_buffer:
                self.db.add(
                    MessageToolCall(
                        message_id=assistant_msg.id,
                        tool_call_id=tc["id"],
                        tool_name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    )
                )
            self.db.commit()

            context_tc_entry: dict[str, Any] = {
                "role": "assistant",
                "tool_calls": tool_calls_buffer,
            }
            if full_content:
                context_tc_entry["content"] = full_content
            if reasoning_content_buffer:
                context_tc_entry["reasoning_content"] = reasoning_content_buffer
            context.append(context_tc_entry)

            pending_skill_confirmation = False
            for tc in tool_calls_buffer:
                prefixed_name = tc["function"]["name"]
                route_info = tool_routing.get(prefixed_name)
                display_name = (
                    route_info["display_name"] if route_info else prefixed_name
                )
                arguments_str = tc["function"]["arguments"]

                if on_event:
                    await on_event(
                        {
                            "type": "tool_call_start",
                            "tool_call_id": tc["id"],
                            "tool_name": display_name,
                            "arguments": arguments_str,
                        }
                    )
                self.set_live_status(
                    conversation_id,
                    status="running",
                    stage="tool_running",
                    stage_detail=f"调用工具中：{display_name}",
                    stage_meta={
                        "phase": "tool_running",
                        "tool_name": display_name,
                        "tool_call_id": tc["id"],
                    },
                    round_no=current_round_no,
                )
                if audit_collector and current_audit_ctx:
                    audit_collector.append_event(
                        current_audit_ctx,
                        event_type="tool_call_started",
                        source="mcp",
                        payload={
                            "tool_call_id": tc["id"],
                            "tool_name": prefixed_name,
                            "arguments": arguments_str,
                        },
                    )

                activation_skill_id: Optional[int] = None
                if prefixed_name.startswith("activate_skill_"):
                    from app.services.skill_activation_manager import (
                        SkillActivationManager,
                    )

                    activation_skill_id = (
                        SkillActivationManager.parse_activation_tool_call(prefixed_name)
                    )

                if (
                    activation_skill_id is not None
                    and activation_skill_id in attempted_activation_skill_ids
                ):
                    tool_result = {
                        "content": json.dumps(
                            {
                                "type": "skill_activation_retry_forbidden",
                                "error": True,
                                "message": (
                                    "同一轮次内不允许再次激活该技能。"
                                    "请等待用户确认结果；若被拒绝，可在下一轮对话再尝试。"
                                ),
                                "skill_id": activation_skill_id,
                                "retry_in_current_turn_forbidden": True,
                            },
                            ensure_ascii=False,
                        ),
                        "error": (
                            "同一轮次内不允许再次激活该技能。"
                            "请等待用户确认结果；若被拒绝，可在下一轮对话再尝试。"
                        ),
                        "_success": False,
                        "files": [],
                    }
                else:
                    if activation_skill_id is not None:
                        attempted_activation_skill_ids.add(activation_skill_id)

                    tool_task = asyncio.create_task(
                        self._execute_tool_call(
                            tc=tc,
                            route_info=route_info,
                            mcp_config_cache=mcp_config_cache,
                            conversation_id=conversation_id,
                            assistant_msg_id=assistant_msg.id if persist_logs else None,
                            persist_logs=persist_logs,
                            persist_generated_files=persist_generated_files,
                        )
                    )
                    progress_tick = 0
                    started_at = time.monotonic()
                    try:
                        while not tool_task.done():
                            await asyncio.sleep(1)
                            if tool_task.done():
                                break
                            progress_tick += 1
                            elapsed_ms = int((time.monotonic() - started_at) * 1000)
                            elapsed_seconds = max(1, elapsed_ms // 1000)
                            self.set_live_status(
                                conversation_id,
                                status="running",
                                stage="tool_running",
                                stage_detail=(
                                    f"调用工具中：{display_name}（已等待 {elapsed_seconds}s）"
                                ),
                                stage_meta={
                                    "phase": "tool_running",
                                    "tool_name": display_name,
                                    "tool_call_id": tc["id"],
                                    "progress_tick": progress_tick,
                                    "elapsed_ms": elapsed_ms,
                                    "elapsed_seconds": elapsed_seconds,
                                },
                                round_no=current_round_no,
                            )
                            if on_event:
                                await on_event(
                                    {
                                        "type": "tool_call_progress",
                                        "tool_call_id": tc["id"],
                                        "tool_name": display_name,
                                        "progress_tick": progress_tick,
                                        "elapsed_ms": elapsed_ms,
                                        "elapsed_seconds": elapsed_seconds,
                                    }
                                )
                        tool_result = await tool_task
                    except asyncio.CancelledError:
                        tool_task.cancel()
                        raise

                print(
                    f"[SkillActivation] Tool result: _success={tool_result.get('_success')}, _skill_activation={tool_result.get('_skill_activation')}"
                )
                if tool_result.get("_success"):
                    skill_activation_data = tool_result.get("_skill_activation")
                    print(
                        f"[SkillActivation] skill_activation_data: {skill_activation_data}"
                    )
                    if skill_activation_data and on_event:
                        print(
                            f"[SkillActivation] Sending skill_activation_request event: skill_id={skill_activation_data['skill_id']}, skill_name={skill_activation_data['skill_name']}"
                        )
                        await on_event(
                            {
                                "type": "skill_activation_request",
                                "tool_call_id": tc["id"],
                                "skill_id": skill_activation_data["skill_id"],
                                "skill_name": skill_activation_data["skill_name"],
                                "skill_description": skill_activation_data[
                                    "skill_description"
                                ],
                            }
                        )
                        print(
                            "[SkillActivation] skill_activation_request event sent successfully"
                        )
                        tool_result["content"] = json.dumps(
                            {
                                "type": "skill_activation_pending",
                                "message": (
                                    f"已向用户发送「{skill_activation_data['skill_name']}」激活请求，请等待用户确认。"
                                    "当前轮次请勿再次调用该技能；若用户拒绝，可在下一轮再尝试。"
                                ),
                                "skill_id": skill_activation_data["skill_id"],
                                "skill_name": skill_activation_data["skill_name"],
                                "retry_in_current_turn_forbidden": True,
                            },
                            ensure_ascii=False,
                        )
                    if on_event:
                        await on_event(
                            {
                                "type": "tool_call_result",
                                "tool_call_id": tc["id"],
                                "success": True,
                                "result_preview": tool_result["content"][:200],
                            }
                        )
                    if tool_result.get("files") and on_event:
                        await on_event(
                            {
                                "type": "tool_call_files",
                                "tool_call_id": tc["id"],
                                "files": tool_result["files"],
                            }
                        )
                    if skill_activation_data:
                        pending_skill_confirmation = True
                    self.set_live_status(
                        conversation_id,
                        status="running",
                        stage="tool_finished",
                        stage_detail=f"调用工具完成：{display_name}",
                        stage_meta={
                            "phase": "tool_finished",
                            "tool_name": display_name,
                            "tool_call_id": tc["id"],
                            "success": True,
                        },
                        round_no=current_round_no,
                    )
                else:
                    if on_event:
                        await on_event(
                            {
                                "type": "tool_call_error",
                                "tool_call_id": tc["id"],
                                "error_message": tool_result.get("error", "未知错误"),
                            }
                        )
                    if audit_collector and current_audit_ctx:
                        audit_collector.append_event(
                            current_audit_ctx,
                            event_type="tool_call_failed",
                            source="mcp",
                            payload={
                                "tool_call_id": tc["id"],
                                "tool_name": prefixed_name,
                                "result": tool_result.get("content"),
                            },
                            error_message=tool_result.get("error", "未知错误"),
                        )
                    self.set_live_status(
                        conversation_id,
                        status="running",
                        stage="tool_finished",
                        stage_detail=f"调用工具失败：{display_name}",
                        stage_meta={
                            "phase": "tool_finished",
                            "tool_name": display_name,
                            "tool_call_id": tc["id"],
                            "success": False,
                        },
                        round_no=current_round_no,
                    )
                if tool_result.get("_success") and audit_collector and current_audit_ctx:
                    audit_collector.append_event(
                        current_audit_ctx,
                        event_type="tool_call_finished",
                        source="mcp",
                        payload={
                            "tool_call_id": tc["id"],
                            "tool_name": prefixed_name,
                            "result": tool_result.get("content"),
                        },
                    )

                tool_msg = Message(
                    conversation_id=conversation_id,
                    role="tool",
                    content=tool_result["content"],
                    tool_call_id=tc["id"],
                    tool_name=prefixed_name,
                    parent_id=assistant_msg.id,
                    is_active=is_active,
                )
                self.db.add(tool_msg)
                self.db.flush()
                last_msg_parent_id = tool_msg.id
                context.append(
                    {
                        "role": "tool",
                        "content": tool_result["content"],
                        "tool_call_id": tc["id"],
                    }
                )

            self.db.commit()
            if pending_skill_confirmation:
                if audit_collector and current_audit_ctx:
                    audit_collector.finish_trace(current_audit_ctx.trace_id)
                    self.db.commit()
                if on_event:
                    await on_event(
                        {
                            "type": "done",
                            "message_id": assistant_msg.id,
                            "waiting_for_skill_confirmation": True,
                        }
                    )
                return {
                    "message_id": assistant_msg.id,
                    "content": full_content,
                    "tool_rounds": tool_round,
                    "output_tokens": total_output,
                    "waiting_for_skill_confirmation": True,
                }

    def _infer_round_no(self, conversation_id: int, parent_message_id: int) -> int:
        try:
            from app.models.message import Message

            count = (
                self.db.query(Message)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.role == "user",
                    Message.id <= parent_message_id,
                )
                .count()
            )
            return max(1, count)
        except Exception:
            return 1
