"""Fallback 容灾服务"""
import asyncio
from typing import Optional, Callable, AsyncGenerator
from sqlalchemy.orm import Session

from app.models.model_fallback import ModelFallbackConfig, ModelFallbackLog
from app.models.model_provider import ModelItem, ModelProvider
from app.services.llm.provider_factory import ProviderFactory


class FallbackService:
    """模型 Fallback 容灾服务"""
    
    # 可 Fallback 的错误类型
    FALLBACK_ERROR_TYPES = {
        "rate_limit": ["rate_limit", "429", "too many requests"],
        "overloaded": ["overloaded", "503", "service unavailable"],
        "timeout": ["timeout", "timed out", "readtimeout", "read timeout"],
        "network": [
            "connecterror",
            "connection refused",
            "connection reset",
            "remoteprotocolerror",
            "broken pipe",
            "eof",
            "network",
            "dns",
            "name or service not known",
            "temporary failure in name resolution",
        ],
        "model_unavailable": ["model not found", "model unavailable"],
    }
    PRIMARY_RETRY_ATTEMPTS = 2
    FALLBACK_RETRY_ATTEMPTS = 1
    
    def __init__(self, db: Session):
        self.db = db
    
    def classify_error(self, error: Exception) -> tuple[bool, str]:
        """
        分类错误，判断是否可以 Fallback
        
        Returns:
            (can_fallback, error_type)
        """
        error_msg = str(error).lower()
        
        for error_type, keywords in self.FALLBACK_ERROR_TYPES.items():
            if any(kw in error_msg for kw in keywords):
                return True, error_type
        
        # 不可 Fallback 的错误：认证失败、参数错误等
        if any(kw in error_msg for kw in ["auth", "invalid", "bad request", "400", "401", "403"]):
            return False, "client_error"
        
        # 默认不 Fallback
        return False, "unknown"

    def is_retryable_error(self, error: Exception) -> bool:
        error_msg = str(error).lower()
        retry_keywords = [
            "timeout",
            "timed out",
            "readtimeout",
            "connecterror",
            "connection refused",
            "connection reset",
            "remoteprotocolerror",
            "broken pipe",
            "network",
            "temporarily unavailable",
            "503",
        ]
        return any(kw in error_msg for kw in retry_keywords)

    async def _call_with_retry(
        self,
        provider_id: int,
        model_name: str,
        call_func: Callable,
        attempts: int,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                provider = ProviderFactory.get_provider(provider_id, self.db)
                call_kwargs = {**kwargs, "model": model_name}
                async for event in call_func(provider, **call_kwargs):
                    yield event
                return
            except Exception as e:
                last_error = e
                if attempt >= attempts or not self.is_retryable_error(e):
                    raise
                await asyncio.sleep(min(0.6 * attempt, 1.5))

        if last_error is not None:
            raise last_error

    def get_fallback_chain(
        self,
        provider_id: int,
        model_name: str
    ) -> list[dict]:
        """
        获取 Fallback 链
        
        优先级：
        1. 特定模型的配置
        2. 特定提供商的配置
        3. 全局默认配置
        """
        # 查找特定模型配置
        config = self.db.query(ModelFallbackConfig).filter(
            ModelFallbackConfig.source_provider_id == provider_id,
            ModelFallbackConfig.source_model_name == model_name,
            ModelFallbackConfig.is_enabled == True
        ).order_by(ModelFallbackConfig.priority.desc()).first()
        
        if config:
            return config.fallback_chain
        
        # 查找提供商配置
        config = self.db.query(ModelFallbackConfig).filter(
            ModelFallbackConfig.source_provider_id == provider_id,
            ModelFallbackConfig.source_model_name == None,
            ModelFallbackConfig.is_enabled == True
        ).order_by(ModelFallbackConfig.priority.desc()).first()
        
        if config:
            return config.fallback_chain
        
        # 查找全局默认配置
        config = self.db.query(ModelFallbackConfig).filter(
            ModelFallbackConfig.source_provider_id == None,
            ModelFallbackConfig.source_model_name == None,
            ModelFallbackConfig.is_enabled == True
        ).order_by(ModelFallbackConfig.priority.desc()).first()
        
        if config:
            return config.fallback_chain
        
        # 无配置时，自动使用“当前可用模型”作为兜底链，降低瞬时故障对用户的影响
        candidates = (
            self.db.query(ModelItem)
            .join(ModelProvider, ModelProvider.id == ModelItem.provider_id)
            .filter(
                ModelProvider.is_enabled == True,
                ModelItem.is_enabled == True,
            )
            .order_by(ModelItem.is_default.desc(), ModelItem.id.asc())
            .limit(8)
            .all()
        )
        auto_chain: list[dict] = []
        for item in candidates:
            if item.provider_id == provider_id and item.model_name == model_name:
                continue
            auto_chain.append({"provider_id": item.provider_id, "model_name": item.model_name})
            if len(auto_chain) >= 3:
                break
        return auto_chain
    
    def log_fallback(
        self,
        conversation_id: int,
        message_id: Optional[int],
        original_provider_id: int,
        original_model_name: str,
        fallback_provider_id: int,
        fallback_model_name: str,
        error_type: str,
        error_message: str
    ):
        """记录 Fallback 日志"""
        log = ModelFallbackLog(
            conversation_id=conversation_id,
            message_id=message_id,
            original_provider_id=original_provider_id,
            original_model_name=original_model_name,
            fallback_provider_id=fallback_provider_id,
            fallback_model_name=fallback_model_name,
            error_type=error_type,
            error_message=error_message[:500] if error_message else None
        )
        self.db.add(log)
        self.db.commit()
    
    async def call_with_fallback(
        self,
        provider_id: int,
        model_name: str,
        call_func: Callable,
        conversation_id: int,
        message_id: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[dict, None]:
        """
        带 Fallback 的模型调用
        
        Args:
            provider_id: 主模型提供商 ID
            model_name: 主模型名称
            call_func: 调用函数（接收 provider, model_name, **kwargs）
            conversation_id: 对话 ID
            message_id: 消息 ID
            **kwargs: 传递给 call_func 的参数（不包含 model）
        """
        fallback_chain = self.get_fallback_chain(provider_id, model_name)
        
        # 尝试主模型（带有限重试，优先消化瞬时网络抖动）
        try:
            async for event in self._call_with_retry(
                provider_id=provider_id,
                model_name=model_name,
                call_func=call_func,
                attempts=self.PRIMARY_RETRY_ATTEMPTS,
                **kwargs,
            ):
                yield event
            return
        except Exception as e:
            can_fallback, error_type = self.classify_error(e)
            trigger_error_message = str(e)
            
            if not can_fallback or not fallback_chain:
                raise
            
            # 发送 Fallback 通知事件
            yield {
                "type": "fallback_triggered",
                "original_model": f"{provider_id}:{model_name}",
                "error_type": error_type,
                "error_message": trigger_error_message[:200]
            }
        
        # 尝试 Fallback 链
        for idx, fallback in enumerate(fallback_chain):
            fallback_provider_id = fallback["provider_id"]
            fallback_model_name = fallback["model_name"]
            
            try:
                # 记录 Fallback
                self.log_fallback(
                    conversation_id=conversation_id,
                    message_id=message_id,
                    original_provider_id=provider_id,
                    original_model_name=model_name,
                    fallback_provider_id=fallback_provider_id,
                    fallback_model_name=fallback_model_name,
                    error_type=error_type,
                    error_message=trigger_error_message
                )
                
                # 发送切换通知
                yield {
                    "type": "fallback_switched",
                    "fallback_model": f"{fallback_provider_id}:{fallback_model_name}",
                    "attempt": idx + 1
                }
                
                # 尝试调用（fallback 节点默认重试 1 次）
                async for event in self._call_with_retry(
                    provider_id=fallback_provider_id,
                    model_name=fallback_model_name,
                    call_func=call_func,
                    attempts=self.FALLBACK_RETRY_ATTEMPTS,
                    **kwargs,
                ):
                    yield event
                return
                
            except Exception as fallback_error:
                can_fallback, _ = self.classify_error(fallback_error)
                
                # 如果是最后一个 Fallback 或不可 Fallback，抛出错误
                if idx == len(fallback_chain) - 1 or not can_fallback:
                    raise fallback_error
                
                # 继续尝试下一个
                continue
