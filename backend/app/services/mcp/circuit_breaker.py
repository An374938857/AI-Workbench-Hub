import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    MCP 熔断器。

    - CLOSED: 正常，允许调用
    - OPEN: 熔断，拒绝调用，等待恢复时间
    - HALF_OPEN: 半开，允许一个探测请求，成功则恢复，失败则继续熔断
    """

    def __init__(self, mcp_id: int, threshold: int = 5, recovery_seconds: int = 300):
        self.mcp_id = mcp_id
        self.threshold = threshold
        self.recovery_seconds = recovery_seconds
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._open_until: datetime | None = None
        self._half_open_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._open_until:
            if datetime.now() >= self._open_until:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def health_status(self) -> str:
        s = self.state
        if s == CircuitState.CLOSED:
            return "healthy"
        elif s == CircuitState.OPEN:
            return "circuit_open"
        else:
            return "degraded"

    async def can_execute(self) -> bool:
        async with self._lock:
            s = self.state
            if s == CircuitState.CLOSED:
                return True
            if s == CircuitState.HALF_OPEN:
                if not self._half_open_in_flight:
                    self._half_open_in_flight = True
                    return True
                return False
            return False

    async def record_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            self._open_until = None
            self._half_open_in_flight = False
            logger.info(f"CircuitBreaker[mcp_id={self.mcp_id}] → CLOSED (success)")

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._half_open_in_flight = False

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._open_until = datetime.now() + timedelta(seconds=self.recovery_seconds)
                logger.warning(
                    f"CircuitBreaker[mcp_id={self.mcp_id}] HALF_OPEN → OPEN "
                    f"(probe failed, retry after {self.recovery_seconds}s)"
                )
            elif self._failure_count >= self.threshold:
                self._state = CircuitState.OPEN
                self._open_until = datetime.now() + timedelta(seconds=self.recovery_seconds)
                logger.warning(
                    f"CircuitBreaker[mcp_id={self.mcp_id}] CLOSED → OPEN "
                    f"(failures={self._failure_count}, threshold={self.threshold})"
                )

    def reset(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._open_until = None
        self._half_open_in_flight = False


class CircuitBreakerRegistry:
    """全局熔断器注册表，按 mcp_id 管理"""

    def __init__(self):
        self._breakers: dict[int, CircuitBreaker] = {}

    def get_or_create(self, mcp_id: int, threshold: int = 5, recovery_seconds: int = 300) -> CircuitBreaker:
        if mcp_id not in self._breakers:
            self._breakers[mcp_id] = CircuitBreaker(mcp_id, threshold, recovery_seconds)
        else:
            cb = self._breakers[mcp_id]
            cb.threshold = threshold
            cb.recovery_seconds = recovery_seconds
        return self._breakers[mcp_id]

    def reset(self, mcp_id: int) -> None:
        if mcp_id in self._breakers:
            self._breakers[mcp_id].reset()

    def remove(self, mcp_id: int) -> None:
        self._breakers.pop(mcp_id, None)


_registry = CircuitBreakerRegistry()


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    return _registry
