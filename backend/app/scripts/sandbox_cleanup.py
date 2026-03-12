#!/usr/bin/env python
"""
沙箱清理定时任务脚本
定时清理超时的对话沙箱

使用方法:
    python -m app.scripts.sandbox_cleanup
    python -m app.scripts.sandbox_cleanup --days 3  # 自定义超时天数
    python -m app.scripts.sandbox_cleanup --daemon  # 守护进程模式
"""
import argparse
import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_cleanup(days: int = 7):
    """执行一次清理任务"""
    from app.tasks.sandbox_cleanup_task import SandboxCleanupTask

    logger.info(f"开始沙箱清理任务（超时天数: {days}）...")
    task = SandboxCleanupTask(timeout_days=days)
    result = task.run()

    if result["success"]:
        logger.info(
            f"清理完成: 总计 {result['total']} 个，成功 {result['succeeded']} 个，失败 {result['failed']} 个"
        )
        if result["failed"] > 0:
            logger.warning(f"失败详情: {result['details']}")
        return 0
    else:
        logger.error(f"清理任务失败: {result.get('error')}")
        return 1


def run_daemon(interval_hours: int = 24):
    """守护进程模式：定期执行清理任务"""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    logger.info(f"启动沙箱清理守护进程（间隔: {interval_hours}小时）...")

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_cleanup,
        trigger=IntervalTrigger(hours=interval_hours),
        id="sandbox_cleanup",
        name="沙箱清理任务",
        replace_existing=True,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("收到退出信号，停止守护进程...")
        scheduler.shutdown()


def main():
    parser = argparse.ArgumentParser(description="沙箱清理定时任务")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="超时天数（默认: 7天）",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="守护进程模式",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=24,
        help="守护进程模式下的执行间隔（小时，默认: 24）",
    )

    args = parser.parse_args()

    if args.daemon:
        # 尝试导入APScheduler，如果不存在则提示安装
        from importlib.util import find_spec

        if find_spec("apscheduler") is None:
            logger.error("守护进程模式需要安装 APScheduler: pip install APScheduler")
            logger.info("请使用 --days 参数执行单次清理，或安装 APScheduler 后使用 --daemon")
            return 1
        return run_daemon(args.interval)
    else:
        return run_cleanup(args.days)


if __name__ == "__main__":
    sys.exit(main())
