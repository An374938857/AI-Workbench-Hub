"""
沙箱定时清理任务
定时清理超时的对话沙箱
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.conversation import Conversation
from app.services.sandbox_file_manager import SandboxFileManager

logger = logging.getLogger(__name__)

# 默认超时天数：7天
DEFAULT_SANDBOX_TIMEOUT_DAYS = 7


class SandboxCleanupTask:
    """沙箱定时清理任务"""

    def __init__(self, timeout_days: int = DEFAULT_SANDBOX_TIMEOUT_DAYS):
        self.timeout_days = timeout_days
        self.sandbox_manager = SandboxFileManager()
        self.settings = get_settings()

    def get_timeout_threshold(self) -> datetime:
        """
        获取超时阈值时间

        Returns:
            超时阈值时间（当前时间 - 超时天数）
        """
        return datetime.now() - timedelta(days=self.timeout_days)

    def get_overdue_conversations(self, db: Session) -> list[Conversation]:
        """
        获取超时的对话列表

        Args:
            db: 数据库会话

        Returns:
            超时对话列表
        """
        threshold = self.get_timeout_threshold()

        # 获取超时的对话（last_activity_at 早于阈值，且未清理）
        conversations = db.query(Conversation).filter(
            Conversation.last_activity_at < threshold,
            Conversation.sandbox_cleaned == False,  # noqa: E712
            Conversation.status.in_(["completed", "closed"])
        ).all()

        logger.info(f"发现 {len(conversations)} 个超时对话（阈值: {threshold.isoformat()}）")
        return conversations

    def cleanup_conversation(self, db: Session, conversation_id: int) -> dict:
        """
        清理单个对话的沙箱

        Args:
            db: 数据库会话
            conversation_id: 对话 ID

        Returns:
            清理结果
        """
        try:
            # 清理沙箱文件
            result = self.sandbox_manager.cleanup_sandbox(conversation_id)

            if result["success"]:
                # 更新数据库标记
                conversation = db.query(Conversation).filter(
                    Conversation.id == conversation_id
                ).first()
                if conversation:
                    conversation.sandbox_cleaned = True
                    db.commit()

                logger.info(f"清理对话 {conversation_id} 的沙箱成功，释放 {result.get('freed_size', 0)} bytes")
                return {
                    "success": True,
                    "conversation_id": conversation_id,
                    "freed_size": result.get("freed_size", 0)
                }
            else:
                logger.warning(f"清理对话 {conversation_id} 的沙箱失败: {result.get('message')}")
                return {
                    "success": False,
                    "conversation_id": conversation_id,
                    "error": result.get("message")
                }

        except Exception as e:
            logger.error(f"清理对话 {conversation_id} 的沙箱异常: {e}", exc_info=True)
            return {
                "success": False,
                "conversation_id": conversation_id,
                "error": str(e)
            }

    def run(self, db: Optional[Session] = None) -> dict:
        """
        执行清理任务

        Args:
            db: 数据库会话（可选，默认创建新会话）

        Returns:
            执行结果汇总
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            # 获取超时对话
            overdue_conversations = self.get_overdue_conversations(db)

            if not overdue_conversations:
                logger.info("没有超时的对话需要清理")
                return {
                    "success": True,
                    "total": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "details": []
                }

            results = []
            succeeded = 0
            failed = 0

            for conversation in overdue_conversations:
                result = self.cleanup_conversation(db, conversation.id)
                results.append(result)

                if result["success"]:
                    succeeded += 1
                else:
                    failed += 1

            logger.info(f"沙箱清理完成: 总计 {len(overdue_conversations)} 个，成功 {succeeded} 个，失败 {failed} 个")

            return {
                "success": True,
                "total": len(overdue_conversations),
                "succeeded": succeeded,
                "failed": failed,
                "details": results
            }

        except Exception as e:
            logger.error(f"沙箱清理任务异常: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "total": 0,
                "succeeded": 0,
                "failed": 0,
                "details": []
            }
        finally:
            if close_db:
                db.close()


# 全局任务实例
_cleanup_task: Optional[SandboxCleanupTask] = None


def get_cleanup_task() -> SandboxCleanupTask:
    """获取清理任务实例（单例）"""
    global _cleanup_task
    if _cleanup_task is None:
        settings = get_settings()
        timeout_days = getattr(settings, "SANDBOX_CLEANUP_DAYS", DEFAULT_SANDBOX_TIMEOUT_DAYS)
        _cleanup_task = SandboxCleanupTask(timeout_days=timeout_days)
    return _cleanup_task


def run_sandbox_cleanup():
    """运行沙箱清理任务（供调度器调用）"""
    task = get_cleanup_task()
    return task.run()