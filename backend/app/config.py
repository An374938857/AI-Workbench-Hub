from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # 数据库配置（Docker环境会通过环境变量覆盖）
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/ai_platform?charset=utf8mb4"

    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_EXPIRE_HOURS: int = 24

    ENCRYPTION_KEY: str = ""

    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 10

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    MCP_MAX_TOOL_ROUNDS: int = 10
    MCP_TOOL_RESULT_MAX_CHARS: int = 16384
    MCP_DEFAULT_TIMEOUT: int = 30
    MCP_CONNECTION_POOL_SIZE: int = 20
    MCP_ENABLED: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    CONVERSATION_EVENTS_HEARTBEAT_SEC: int = 15

    # 搜索和推荐配置（Docker环境会通过环境变量覆盖）
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    CHROMA_URL: str = "http://localhost:8000"
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    
    # 搜索配置
    SEARCH_CACHE_TTL: int = 300  # 5分钟
    SEARCH_MAX_RESULTS: int = 20
    
    # 推荐配置
    RECOMMEND_CACHE_TTL: int = 300
    RECOMMEND_TOP_K: int = 3
    RECOMMEND_USAGE_WEIGHT: float = 0.4
    RECOMMEND_SIMILARITY_WEIGHT: float = 0.6
    REFERENCE_RECOMMEND_TIMEOUT_SEC: float = 8.0
    REFERENCE_SCOPE_SNAPSHOT_TTL_SEC: int = 120
    REFERENCE_VECTOR_MIN_CATALOG_SIZE: int = 12
    REFERENCE_RECOMMEND_USE_VECTOR: bool = False
    
    # 压缩配置
    COMPRESSION_THRESHOLD: int = 30  # 轮数
    COMPRESSION_KEEP_RECENT: int = 20  # 保留最近消息数

    # 图片上传配置
    BASE_URL: str = "http://localhost:8000"
    IMAGE_DELIVERY_MODE: str = "base64"  # "url" 或 "base64"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("UPLOAD_DIR", mode="before")
    @classmethod
    def resolve_upload_dir(cls, value: str) -> str:
        if value is None:
            return str(BACKEND_ROOT / "uploads")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return str(path.resolve())


@lru_cache
def get_settings() -> Settings:
    return Settings()
