"""Circuit breaker pattern for external service resilience.

Supports:
- Closed / Open / Half-Open states
- Configurable failure threshold and recovery timeout
- Half-open probe with limited request allowance
- Metrics exposure for monitoring
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = auto()       # Normal operation, requests pass through
    OPEN = auto()         # Failing, requests are fast-failed
    HALF_OPEN = auto()    # Probing, limited requests allowed


@dataclass
class CircuitBreakerMetrics:
    """Exposed metrics for a circuit breaker instance."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    total_calls: int = 0
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    last_state_change_time: float = field(default_factory=time.time)
    state_change_count: int = 0
    open_duration_seconds: float = 0.0
    half_open_allowed: int = 0
    half_open_used: int = 0
    rejected_calls: int = 0


class CircuitBreaker:
    """Circuit breaker for external service calls.

    Prevents cascading failures by stopping calls to a failing service
    and periodically probing for recovery.

    Args:
        name: Service name for logging/metrics
        failure_threshold: Consecutive failures before opening
        recovery_timeout: Seconds before transitioning to half-open
        half_open_max_calls: Max probe calls allowed in half-open state
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        # State
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._total_calls = 0
        self._consecutive_failures = 0
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None
        self._last_state_change_time = time.time()
        self._state_change_count = 0
        self._half_open_used = 0
        self._rejected_calls = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through.

        Returns:
            True if the request is allowed, False if circuit is open.
        """
        self._total_calls += 1

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            elapsed = time.time() - self._last_state_change_time
            if elapsed >= self._recovery_timeout:
                self._transition_to_half_open()
                # Count this probe towards half-open limit
                self._half_open_used += 1
                return True

            self._rejected_calls += 1
            return False

        # Half-open: allow limited probes
        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_used < self._half_open_max_calls:
                self._half_open_used += 1
                return True

            self._rejected_calls += 1
            return False

        return False  # pragma: no cover

    def record_success(self) -> None:
        """Record a successful call."""
        self._success_count += 1
        self._consecutive_failures = 0
        self._last_success_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            logger.info(
                "Circuit breaker '%s' recovered, closing",
                self._name,
            )
            self._transition_to(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._consecutive_failures += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            logger.warning(
                "Circuit breaker '%s' half-open probe failed, reopening",
                self._name,
            )
            self._transition_to(CircuitState.OPEN)
            return

        if (
            self._state == CircuitState.CLOSED
            and self._consecutive_failures >= self._failure_threshold
        ):
            logger.warning(
                "Circuit breaker '%s' opened after %d consecutive failures",
                self._name,
                self._consecutive_failures,
            )
            self._transition_to(CircuitState.OPEN)

    def get_metrics(self) -> CircuitBreakerMetrics:
        """Get current circuit breaker metrics."""
        now = time.time()
        open_duration = 0.0
        if self._state == CircuitState.OPEN:
            open_duration = now - self._last_state_change_time

        return CircuitBreakerMetrics(
            state=self._state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            total_calls=self._total_calls,
            consecutive_failures=self._consecutive_failures,
            last_failure_time=self._last_failure_time,
            last_success_time=self._last_success_time,
            last_state_change_time=self._last_state_change_time,
            state_change_count=self._state_change_count,
            open_duration_seconds=open_duration,
            half_open_allowed=self._half_open_max_calls,
            half_open_used=self._half_open_used,
            rejected_calls=self._rejected_calls,
        )

    def reset(self) -> None:
        """Force reset circuit breaker to closed state."""
        logger.info("Circuit breaker '%s' manually reset", self._name)
        self._failure_count = 0
        self._success_count = 0
        self._consecutive_failures = 0
        self._half_open_used = 0
        self._rejected_calls = 0
        self._transition_to(CircuitState.CLOSED)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._last_state_change_time = time.time()
        self._state_change_count += 1

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_used = 0

        logger.debug(
            "Circuit breaker '%s' state: %s -> %s",
            self._name,
            old_state.name,
            new_state.name,
        )

    def _transition_to_half_open(self) -> None:
        """Transition from open to half-open."""
        self._transition_to(CircuitState.HALF_OPEN)
        logger.info(
            "Circuit breaker '%s' transitioning to half-open for probing",
            self._name,
        )


# ------------------------------------------------------------------
# Circuit breaker registry for centralized access
# ------------------------------------------------------------------

class CircuitBreakerRegistry:
    """Registry of named circuit breakers for all external services."""

    _instance: Optional["CircuitBreakerRegistry"] = None

    def __new__(cls) -> "CircuitBreakerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._breakers: dict[str, CircuitBreaker] = {}
        return cls._instance

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create a new one.

        Args:
            name: Service name
            failure_threshold: Consecutive failures before opening
            recovery_timeout: Seconds before half-open probe
            half_open_max_calls: Max probe calls in half-open

        Returns:
            CircuitBreaker instance
        """
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
            )
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get existing circuit breaker by name."""
        return self._breakers.get(name)

    def get_all_metrics(self) -> dict[str, CircuitBreakerMetrics]:
        """Get metrics for all registered circuit breakers."""
        return {
            name: breaker.get_metrics()
            for name, breaker in self._breakers.items()
        }

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()

    def reset(self, name: str) -> None:
        """Reset a specific circuit breaker."""
        breaker = self._breakers.get(name)
        if breaker:
            breaker.reset()