"""
初始化提示词模板数据
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.system_prompt_template import SystemPromptTemplate


def init_prompt_templates():
    """初始化内置提示词模板（已停用）。"""
    db: Session = SessionLocal()

    try:
        existing_count = db.query(SystemPromptTemplate).filter(
            SystemPromptTemplate.is_builtin == True
        ).count()
        print(f"内置提示词初始化已停用，当前内置模板数：{existing_count}")

    except Exception as e:
        db.rollback()
        print(f"初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_prompt_templates()
