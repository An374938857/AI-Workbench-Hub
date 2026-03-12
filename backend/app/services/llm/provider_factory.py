from sqlalchemy.orm import Session

from app.models.model_provider import ModelProvider
from app.services.llm.base import BaseLLMProvider
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.llm.anthropic_provider import AnthropicProvider
from app.utils.crypto import decrypt_api_key


class ProviderFactory:

    _cache: dict[int, BaseLLMProvider] = {}

    PROTOCOL_MAP: dict[str, type[BaseLLMProvider]] = {
        "openai_compatible": OpenAICompatibleProvider,
        "anthropic": AnthropicProvider,
    }

    @classmethod
    def get_provider(cls, provider_id: int, db: Session) -> BaseLLMProvider:
        if provider_id in cls._cache:
            return cls._cache[provider_id]

        record = db.query(ModelProvider).filter(ModelProvider.id == provider_id).first()
        if not record:
            raise ValueError(f"模型提供商 ID={provider_id} 不存在")
        if not record.is_enabled:
            raise ValueError("当前模型服务不可用，请联系管理员")

        api_key = decrypt_api_key(record.api_key_encrypted)

        provider_cls = cls.PROTOCOL_MAP.get(record.protocol_type)
        if not provider_cls:
            raise ValueError(f"不支持的协议类型: {record.protocol_type}")

        provider = provider_cls(record.api_base_url, api_key)
        cls._cache[provider_id] = provider
        return provider

    @classmethod
    def clear_cache(cls, provider_id: int = None):
        if provider_id:
            cls._cache.pop(provider_id, None)
        else:
            cls._cache.clear()
