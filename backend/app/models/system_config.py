from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SystemConfig(Base):
    """系统配置表"""
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="string")  # string, int, bool, json
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now, onupdate=datetime.now
    )

    __table_args__ = (
        Index("idx_config_key", "key"),
    )

    def get_value(self):
        """根据类型返回转换后的值"""
        if self.value is None:
            return None

        if self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        elif self.value_type == "int":
            try:
                return int(self.value)
            except ValueError:
                return 0
        elif self.value_type == "json":
            import json
            try:
                return json.loads(self.value)
            except json.JSONDecodeError:
                return None
        else:
            return self.value

    def set_value(self, value) -> None:
        """设置值并转换类型"""
        if value is None:
            self.value = None
            self.value_type = "string"
        elif isinstance(value, bool):
            self.value = "true" if value else "false"
            self.value_type = "bool"
        elif isinstance(value, int):
            self.value = str(value)
            self.value_type = "int"
        elif isinstance(value, (dict, list)):
            import json
            self.value = json.dumps(value, ensure_ascii=False)
            self.value_type = "json"
        else:
            self.value = str(value)
            self.value_type = "string"