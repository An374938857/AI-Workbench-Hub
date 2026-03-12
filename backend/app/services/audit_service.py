import hashlib
import json
import os
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.conversation import Conversation
from app.models.conversation_audit import (
    ConversationAuditArchive,
    ConversationAuditEvent,
    ConversationAuditTrace,
)
from app.models.conversation_tag import ConversationTagRelation
from app.models.message import Message
from app.models.user import User

settings = get_settings()

ABNORMAL_EVENT_TYPES = {
    "llm_error": "llm_error",
    "tool_call_failed": "tool_call_failed",
    "request_timeout": "request_timeout",
    "stream_interrupted": "stream_interrupted",
}


@dataclass
class AuditContext:
    trace_id: str
    conversation_id: int
    user_id: int
    round_no: int


class AuditEventWriter:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def compute_payload_sha256(payload_raw: str) -> str:
        payload_bytes = payload_raw.encode("utf-8")
        return hashlib.sha256(payload_bytes).hexdigest()

    def verify_payload(self, payload_raw: str, payload_sha256: str) -> tuple[bool, Optional[str]]:
        expected = self.compute_payload_sha256(payload_raw)
        if expected == payload_sha256:
            return True, None
        return False, f"hash mismatch: expected {expected}, got {payload_sha256}"

    def append_event(
        self,
        *,
        trace_id: str,
        conversation_id: int,
        message_id: Optional[int],
        round_no: int,
        event_type: str,
        source: str,
        payload_raw: str,
        event_time: Optional[datetime] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> ConversationAuditEvent:
        payload_sha256 = self.compute_payload_sha256(payload_raw)
        event = ConversationAuditEvent(
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            round_no=round_no,
            event_type=event_type,
            event_time=event_time or datetime.now(),
            source=source,
            payload_raw=payload_raw,
            payload_sha256=payload_sha256,
            verify_status="passed",
            error_code=error_code,
            error_message=error_message,
        )
        self.db.add(event)
        return event


class AuditEventCollector:
    def __init__(self, db: Session):
        self.db = db
        self.writer = AuditEventWriter(db)

    def init_trace(self, conversation_id: int, user_id: int, round_no: int) -> AuditContext:
        trace_id = f"trc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:12]}"
        trace = ConversationAuditTrace(
            trace_id=trace_id,
            conversation_id=conversation_id,
            user_id=user_id,
            started_at=datetime.now(),
            is_abnormal=False,
            abnormal_types=None,
        )
        self.db.add(trace)
        self.db.flush()
        return AuditContext(
            trace_id=trace_id,
            conversation_id=conversation_id,
            user_id=user_id,
            round_no=round_no,
        )

    def append_event(
        self,
        ctx: AuditContext,
        *,
        event_type: str,
        source: str,
        payload: dict[str, Any] | list[Any] | str,
        message_id: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        if isinstance(payload, str):
            payload_raw = payload
        else:
            payload_raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        self.writer.append_event(
            trace_id=ctx.trace_id,
            conversation_id=ctx.conversation_id,
            message_id=message_id,
            round_no=ctx.round_no,
            event_type=event_type,
            source=source,
            payload_raw=payload_raw,
            error_code=error_code,
            error_message=error_message,
        )

        abnormal_type = ABNORMAL_EVENT_TYPES.get(event_type)
        if abnormal_type:
            self._mark_trace_abnormal(ctx.trace_id, abnormal_type)

    def finish_trace(self, trace_id: str) -> None:
        trace = (
            self.db.query(ConversationAuditTrace)
            .filter(ConversationAuditTrace.trace_id == trace_id)
            .first()
        )
        if trace:
            trace.ended_at = datetime.now()

    def _mark_trace_abnormal(self, trace_id: str, abnormal_type: str) -> None:
        trace = (
            self.db.query(ConversationAuditTrace)
            .filter(ConversationAuditTrace.trace_id == trace_id)
            .first()
        )
        if not trace:
            return
        current = trace.abnormal_types or []
        if abnormal_type not in current:
            current.append(abnormal_type)
        trace.abnormal_types = current
        trace.is_abnormal = True


class AuditQueryService:
    def __init__(self, db: Session):
        self.db = db
        export_dir = os.path.join(settings.UPLOAD_DIR, "audit_exports")
        os.makedirs(export_dir, exist_ok=True)
        self.export_dir = export_dir
        if not hasattr(AuditQueryService, "_export_tasks"):
            AuditQueryService._export_tasks = {}

    def list_conversations(
        self,
        *,
        page: int,
        page_size: int,
        user_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        model_name: Optional[str] = None,
        is_abnormal: Optional[bool] = None,
        skill_id: Optional[int] = None,
        mcp_tool: Optional[str] = None,
        conversation_status: Optional[str] = None,
        tag_id: Optional[int] = None,
    ) -> dict[str, Any]:
        query = (
            self.db.query(
                Conversation.id.label("conversation_id"),
                Conversation.user_id,
                User.display_name,
                Conversation.title.label("conversation_title"),
                Conversation.current_model_name.label("model_name"),
                Conversation.last_activity_at,
                Conversation.created_at,
                func.max(ConversationAuditTrace.started_at).label("latest_trace_started_at"),
                func.count(func.distinct(ConversationAuditTrace.trace_id)).label("trace_count"),
                func.max(case((ConversationAuditTrace.is_abnormal == True, 1), else_=0)).label("abnormal_flag"),
            )
            .join(User, User.id == Conversation.user_id)
            .join(
                ConversationAuditTrace,
                ConversationAuditTrace.conversation_id == Conversation.id,
            )
            .group_by(
                Conversation.id,
                Conversation.user_id,
                User.display_name,
                Conversation.title,
                Conversation.current_model_name,
                Conversation.last_activity_at,
                Conversation.created_at,
            )
        )

        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        if start_time:
            query = query.filter(Conversation.last_activity_at >= start_time)
        if end_time:
            query = query.filter(Conversation.last_activity_at <= end_time)
        if model_name:
            query = query.filter(Conversation.current_model_name == model_name)
        if is_abnormal is not None:
            query = query.filter(ConversationAuditTrace.is_abnormal == is_abnormal)
        if skill_id:
            query = query.filter(Conversation.skill_id == skill_id)
        if conversation_status and hasattr(Conversation, "status"):
            query = query.filter(getattr(Conversation, "status") == conversation_status)
        if tag_id:
            query = query.join(
                ConversationTagRelation,
                ConversationTagRelation.conversation_id == Conversation.id,
            ).filter(ConversationTagRelation.tag_id == tag_id)
        if mcp_tool:
            query = query.filter(
                Conversation.id.in_(
                    self.db.query(ConversationAuditEvent.conversation_id)
                    .filter(
                        ConversationAuditEvent.event_type.in_(["tool_call_started", "tool_call_finished", "tool_call_failed"]),
                        ConversationAuditEvent.payload_raw.like(f"%{mcp_tool}%"),
                    )
                )
            )

        total = query.count()
        items = (
            query.order_by(Conversation.last_activity_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        abnormal_map: dict[int, list[str]] = {}
        conv_ids = [row.conversation_id for row in items]
        round_count_map: dict[int, int] = {}
        latest_message_preview_map: dict[int, str] = {}
        if conv_ids:
            abnormal_rows = (
                self.db.query(
                    ConversationAuditTrace.conversation_id,
                    ConversationAuditTrace.abnormal_types,
                )
                .filter(
                    ConversationAuditTrace.conversation_id.in_(conv_ids),
                    ConversationAuditTrace.is_abnormal == True,
                )
                .all()
            )
            for conv_id, abnormal_types in abnormal_rows:
                if conv_id not in abnormal_map:
                    abnormal_map[conv_id] = []
                for abnormal_type in abnormal_types or []:
                    if abnormal_type not in abnormal_map[conv_id]:
                        abnormal_map[conv_id].append(abnormal_type)

            round_count_rows = (
                self.db.query(
                    ConversationAuditEvent.conversation_id,
                    func.count(func.distinct(ConversationAuditEvent.round_no)).label("round_count"),
                )
                .filter(ConversationAuditEvent.conversation_id.in_(conv_ids))
                .group_by(ConversationAuditEvent.conversation_id)
                .all()
            )
            round_count_map = {
                int(row.conversation_id): int(row.round_count or 0)
                for row in round_count_rows
            }

            for conv_id in conv_ids:
                latest_message = (
                    self.db.query(Message.content)
                    .filter(
                        Message.conversation_id == conv_id,
                        Message.role.in_(["user", "assistant"]),
                    )
                    .order_by(Message.id.desc())
                    .first()
                )
                if latest_message and latest_message[0]:
                    preview = str(latest_message[0]).replace("\n", " ").strip()
                    latest_message_preview_map[conv_id] = (
                        preview[:80] + "..." if len(preview) > 80 else preview
                    )

        return {
            "items": [
                {
                    "conversation_id": row.conversation_id,
                    "user_id": row.user_id,
                    "user_name": row.display_name,
                    "conversation_title": row.conversation_title or f"会话 {row.conversation_id}",
                    "latest_message_preview": latest_message_preview_map.get(row.conversation_id, ""),
                    "model_name": row.model_name,
                    "last_activity_at": row.last_activity_at.isoformat() if row.last_activity_at else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "is_abnormal": bool(row.abnormal_flag),
                    "abnormal_types": abnormal_map.get(row.conversation_id, []),
                    "latest_trace_started_at": row.latest_trace_started_at.isoformat()
                    if row.latest_trace_started_at
                    else None,
                    "trace_count": int(row.trace_count or 0),
                    "round_count": round_count_map.get(row.conversation_id, 0),
                }
                for row in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_timeline(self, conversation_id: int, trace_id: Optional[str] = None) -> dict[str, Any]:
        trace_query = self.db.query(ConversationAuditTrace).filter(
            ConversationAuditTrace.conversation_id == conversation_id
        )
        if trace_id:
            trace_query = trace_query.filter(ConversationAuditTrace.trace_id == trace_id)

        traces = trace_query.order_by(ConversationAuditTrace.started_at.desc()).all()
        rounds = defaultdict(
            lambda: {
                "event_count": 0,
                "is_abnormal": False,
                "abnormal_types": set(),
                "trace_ids": set(),
                "start_time": None,
                "end_time": None,
            }
        )

        for trace in traces:
            events = (
                self.db.query(ConversationAuditEvent)
                .filter(ConversationAuditEvent.trace_id == trace.trace_id)
                .order_by(ConversationAuditEvent.event_time.asc(), ConversationAuditEvent.id.asc())
                .all()
            )
            for event in events:
                key = event.round_no
                rounds[key]["event_count"] += 1
                rounds[key]["trace_ids"].add(trace.trace_id)
                if rounds[key]["start_time"] is None or (
                    event.event_time and event.event_time < rounds[key]["start_time"]
                ):
                    rounds[key]["start_time"] = event.event_time
                if rounds[key]["end_time"] is None or (
                    event.event_time and event.event_time > rounds[key]["end_time"]
                ):
                    rounds[key]["end_time"] = event.event_time
                if event.event_type in ABNORMAL_EVENT_TYPES:
                    rounds[key]["is_abnormal"] = True
                    rounds[key]["abnormal_types"].add(ABNORMAL_EVENT_TYPES[event.event_type])

        return {
            "conversation_id": conversation_id,
            "rounds": [
                {
                    "round_no": round_no,
                    "event_count": info["event_count"],
                    "is_abnormal": info["is_abnormal"],
                    "abnormal_types": sorted(list(info["abnormal_types"])),
                    "trace_ids": sorted(list(info["trace_ids"])),
                    "start_time": info["start_time"].isoformat() if info["start_time"] else None,
                    "end_time": info["end_time"].isoformat() if info["end_time"] else None,
                    "duration_seconds": (
                        round(
                            (
                                info["end_time"] - info["start_time"]
                            ).total_seconds(),
                            3,
                        )
                        if info["start_time"] and info["end_time"]
                        else 0
                    ),
                }
                for round_no, info in sorted(rounds.items())
            ],
            "trace_count": len(traces),
        }

    def get_round_detail(self, conversation_id: int, round_no: int) -> dict[str, Any]:
        events = (
            self.db.query(ConversationAuditEvent)
            .filter(
                ConversationAuditEvent.conversation_id == conversation_id,
                ConversationAuditEvent.round_no == round_no,
            )
            .order_by(ConversationAuditEvent.event_time.asc(), ConversationAuditEvent.id.asc())
            .all()
        )

        request_events = [e for e in events if e.event_type == "llm_request_raw"]
        response_events = [e for e in events if e.event_type == "llm_response_raw"]
        tool_events = [
            e
            for e in events
            if e.event_type in ("tool_call_started", "tool_call_finished", "tool_call_failed")
        ]

        writer = AuditEventWriter(self.db)

        def _event_to_dict(event: ConversationAuditEvent) -> dict[str, Any]:
            verified, verify_error = writer.verify_payload(event.payload_raw, event.payload_sha256)
            return {
                "id": event.id,
                "trace_id": event.trace_id,
                "event_type": event.event_type,
                "event_time": event.event_time.isoformat() if event.event_time else None,
                "source": event.source,
                "payload_raw": event.payload_raw,
                "payload_sha256": event.payload_sha256,
                "verify_status": "passed" if verified else "failed",
                "verify_error": verify_error,
                "error_code": event.error_code,
                "error_message": event.error_message,
            }

        return {
            "conversation_id": conversation_id,
            "round_no": round_no,
            "trace_ids": sorted(list({e.trace_id for e in events})),
            "request": [_event_to_dict(e) for e in request_events],
            "response": [_event_to_dict(e) for e in response_events],
            "tool_chain": [_event_to_dict(e) for e in tool_events],
            "events": [_event_to_dict(e) for e in events],
        }

    def get_replay(self, trace_id: str) -> dict[str, Any]:
        events = (
            self.db.query(ConversationAuditEvent)
            .filter(ConversationAuditEvent.trace_id == trace_id)
            .order_by(ConversationAuditEvent.event_time.asc(), ConversationAuditEvent.id.asc())
            .all()
        )
        return {
            "trace_id": trace_id,
            "events": [
                {
                    "id": e.id,
                    "conversation_id": e.conversation_id,
                    "round_no": e.round_no,
                    "event_type": e.event_type,
                    "event_time": e.event_time.isoformat() if e.event_time else None,
                    "source": e.source,
                    "payload_raw": e.payload_raw,
                    "payload_sha256": e.payload_sha256,
                    "verify_status": e.verify_status,
                    "error_code": e.error_code,
                    "error_message": e.error_message,
                }
                for e in events
            ],
        }

    def create_export_task(self, filters: dict[str, Any], export_format: str) -> str:
        task_id = uuid.uuid4().hex
        task = {
            "task_id": task_id,
            "status": "processing",
            "format": export_format,
            "created_at": datetime.now().isoformat(),
            "download_url": None,
            "error": None,
        }
        AuditQueryService._export_tasks[task_id] = task
        self._build_export(task_id, filters, export_format)
        return task_id

    def _build_export(self, task_id: str, filters: dict[str, Any], export_format: str) -> None:
        try:
            page_size = min(int(filters.get("page_size", 2000)), 10000)
            listing = self.list_conversations(
                page=1,
                page_size=page_size,
                user_id=filters.get("user_id"),
                model_name=filters.get("model_name"),
                is_abnormal=filters.get("is_abnormal"),
                skill_id=filters.get("skill_id"),
                mcp_tool=filters.get("mcp_tool"),
                tag_id=filters.get("tag_id"),
            )
            conv_ids = [item["conversation_id"] for item in listing["items"]]
            events = (
                self.db.query(ConversationAuditEvent)
                .filter(ConversationAuditEvent.conversation_id.in_(conv_ids) if conv_ids else False)
                .order_by(ConversationAuditEvent.event_time.asc(), ConversationAuditEvent.id.asc())
                .all()
            )
            event_dicts = [
                {
                    "trace_id": e.trace_id,
                    "conversation_id": e.conversation_id,
                    "message_id": e.message_id,
                    "round_no": e.round_no,
                    "event_type": e.event_type,
                    "event_time": e.event_time.isoformat() if e.event_time else None,
                    "source": e.source,
                    "payload_raw": e.payload_raw,
                    "payload_sha256": e.payload_sha256,
                    "verify_status": e.verify_status,
                    "error_code": e.error_code,
                    "error_message": e.error_message,
                }
                for e in events
            ]

            filename = f"audit_export_{task_id}.{ 'ndjson' if export_format == 'ndjson' else 'json'}"
            filepath = os.path.join(self.export_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                if export_format == "ndjson":
                    for row in event_dicts:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                else:
                    json.dump(event_dicts, f, ensure_ascii=False, indent=2)

            AuditQueryService._export_tasks[task_id].update(
                {
                    "status": "completed",
                    "download_url": f"/api/admin/audit/export/{task_id}/download",
                }
            )
        except Exception as e:
            AuditQueryService._export_tasks[task_id].update(
                {
                    "status": "failed",
                    "error": str(e),
                }
            )

    def get_export_task(self, task_id: str) -> dict[str, Any]:
        task = AuditQueryService._export_tasks.get(task_id)
        if not task:
            return {"task_id": task_id, "status": "not_found", "download_url": None}
        return task

    def get_export_file(self, task_id: str) -> Optional[str]:
        task = self.get_export_task(task_id)
        if task.get("status") != "completed":
            return None
        ext = "ndjson" if task.get("format") == "ndjson" else "json"
        filepath = os.path.join(self.export_dir, f"audit_export_{task_id}.{ext}")
        if os.path.exists(filepath):
            return filepath
        return None


class AuditMetricsService:
    def __init__(self, db: Session):
        self.db = db

    def overview(self, window: str = "day") -> dict[str, Any]:
        now = datetime.now()
        days = 1 if window == "day" else 7 if window == "week" else 30
        start = now - timedelta(days=days)

        total_traces = (
            self.db.query(func.count(ConversationAuditTrace.id))
            .filter(ConversationAuditTrace.started_at >= start)
            .scalar()
            or 0
        )
        abnormal_traces = (
            self.db.query(func.count(ConversationAuditTrace.id))
            .filter(
                ConversationAuditTrace.started_at >= start,
                ConversationAuditTrace.is_abnormal == True,
            )
            .scalar()
            or 0
        )
        total_rounds = (
            self.db.query(ConversationAuditEvent.conversation_id, ConversationAuditEvent.round_no)
            .filter(ConversationAuditEvent.event_time >= start)
            .group_by(ConversationAuditEvent.conversation_id, ConversationAuditEvent.round_no)
            .count()
        )
        request_rounds = (
            self.db.query(ConversationAuditEvent.conversation_id, ConversationAuditEvent.round_no)
            .filter(
                ConversationAuditEvent.event_time >= start,
                ConversationAuditEvent.event_type == "llm_request_raw",
            )
            .group_by(ConversationAuditEvent.conversation_id, ConversationAuditEvent.round_no)
            .all()
        )
        response_rounds = {
            (row.conversation_id, row.round_no)
            for row in self.db.query(
                ConversationAuditEvent.conversation_id,
                ConversationAuditEvent.round_no,
            )
            .filter(
                ConversationAuditEvent.event_time >= start,
                ConversationAuditEvent.event_type == "llm_response_raw",
            )
            .group_by(ConversationAuditEvent.conversation_id, ConversationAuditEvent.round_no)
            .all()
        }
        complete_rounds = sum(1 for row in request_rounds if (row.conversation_id, row.round_no) in response_rounds)

        abnormal_type_rows = (
            self.db.query(ConversationAuditEvent.event_type, func.count(ConversationAuditEvent.id))
            .filter(
                ConversationAuditEvent.event_time >= start,
                ConversationAuditEvent.event_type.in_(
                    ["llm_error", "tool_call_failed", "request_timeout", "stream_interrupted"]
                ),
            )
            .group_by(ConversationAuditEvent.event_type)
            .all()
        )

        abnormal_distribution = [
            {"type": event_type, "count": count}
            for event_type, count in abnormal_type_rows
        ]

        replay_attempts = total_traces
        replay_success = total_traces - abnormal_traces

        return {
            "window": window,
            "total_traces": total_traces,
            "abnormal_traces": abnormal_traces,
            "abnormal_ratio": round(abnormal_traces / total_traces, 4) if total_traces else 0,
            "traceability_coverage": round(complete_rounds / total_rounds, 4) if total_rounds else 0,
            "replay_success_rate": round(replay_success / replay_attempts, 4) if replay_attempts else 0,
            "abnormal_distribution": abnormal_distribution,
        }


class AuditArchiveTask:
    def __init__(self, db: Session):
        self.db = db
        archive_dir = os.path.join(settings.UPLOAD_DIR, "audit_archives")
        os.makedirs(archive_dir, exist_ok=True)
        self.archive_dir = archive_dir

    def run(self) -> dict[str, Any]:
        threshold = datetime.now() - timedelta(days=90)
        events = (
            self.db.query(ConversationAuditEvent)
            .filter(ConversationAuditEvent.event_time < threshold)
            .order_by(ConversationAuditEvent.event_time.asc())
            .all()
        )
        if not events:
            return {"success": True, "record_count": 0, "archive_batch_no": None}

        archive_batch_no = f"arc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        archive_file = os.path.join(self.archive_dir, f"{archive_batch_no}.ndjson")

        lines: list[str] = []
        for e in events:
            lines.append(
                json.dumps(
                    {
                        "trace_id": e.trace_id,
                        "conversation_id": e.conversation_id,
                        "round_no": e.round_no,
                        "event_type": e.event_type,
                        "event_time": e.event_time.isoformat() if e.event_time else None,
                        "source": e.source,
                        "payload_raw": e.payload_raw,
                        "payload_sha256": e.payload_sha256,
                        "verify_status": e.verify_status,
                        "error_code": e.error_code,
                        "error_message": e.error_message,
                    },
                    ensure_ascii=False,
                )
            )

        with open(archive_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        checksum = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

        archive = ConversationAuditArchive(
            archive_batch_no=archive_batch_no,
            archive_date=date.today(),
            storage_uri=archive_file,
            record_count=len(events),
            checksum=checksum,
        )
        self.db.add(archive)

        event_ids = [e.id for e in events]
        self.db.query(ConversationAuditEvent).filter(
            ConversationAuditEvent.id.in_(event_ids)
        ).delete(synchronize_session=False)

        traces_in_use = {
            row[0]
            for row in self.db.query(ConversationAuditEvent.trace_id)
            .filter(ConversationAuditEvent.trace_id.in_({e.trace_id for e in events}))
            .all()
        }
        trace_ids_to_delete = [e.trace_id for e in events if e.trace_id not in traces_in_use]
        if trace_ids_to_delete:
            self.db.query(ConversationAuditTrace).filter(
                ConversationAuditTrace.trace_id.in_(set(trace_ids_to_delete))
            ).delete(synchronize_session=False)

        self.db.commit()

        return {
            "success": True,
            "record_count": len(events),
            "archive_batch_no": archive_batch_no,
            "storage_uri": archive_file,
        }

    def restore_by_trace(self, trace_id: str) -> list[dict[str, Any]]:
        archives = self.db.query(ConversationAuditArchive).order_by(ConversationAuditArchive.created_at.desc()).all()
        for archive in archives:
            if not os.path.exists(archive.storage_uri):
                continue
            restored: list[dict[str, Any]] = []
            with open(archive.storage_uri, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("trace_id") == trace_id:
                        restored.append(record)
            if restored:
                return restored
        return []
