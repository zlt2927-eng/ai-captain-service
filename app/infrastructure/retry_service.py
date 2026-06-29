"""Reusable retry service with exponential backoff, jitter, and retry policies.

Replaces duplicated retry logic across:
- HTTPClient._sleep_backoff / request retry loop
- GeminiOrchestrator._retryable
- RedisClient._retry_async / _retry_call

Supports:
- Exponential backoff with configurable base/max delay
- Jitter for thundering herd prevention
- Retry policies (status code based, exception based)
- Configurable max attempts
- Circuit breaker integration
- Callback hooks (on_retry, on_failure, on_success)
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Optional, TypeVar

from app.infrastructure.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ------------------------------------------------------------------
# Retry Policy Types
# ------------------------------------------------------------------

class RetryDecision(Enum):
    """Decision for a single attempt outcome."""
    RETRY = auto()
    FAIL_FAST = auto()
    SUCCESS = auto()


@dataclass
class RetryPolicy:
    """Policy for determining if an error is retryable.

    Args:
        retryable_exceptions: Exception types that trigger a retry
        retryable_status_codes: HTTP status codes that trigger a retry
        max_attempts: Maximum total attempts (including first)
        base_delay: Base delay in seconds for exponential backoff
        max_delay: Maximum delay in seconds
        jitter_factor: Fraction of delay to use for jitter (0.0 = no jitter)
        use_jitter: Whether to apply jitter
    """
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, OSError)
    retryable_status_codes: set[int] = field(default_factory=lambda: {429, 500, 502, 503, 504})
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter_factor: float = 0.1
    use_jitter: bool = True


# ------------------------------------------------------------------
# Retry Service
# ------------------------------------------------------------------

@dataclass
class RetryAttempt:
    """Information about a single retry attempt."""
    attempt_number: int
    delay_seconds: float
    error: Optional[Exception] = None
    status_code: Optional[int] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = 0.0


@dataclass
class RetryMetrics:
    """Metrics for a retry operation."""
    total_attempts: int = 0
    successful_attempt: int = 0
    total_duration_ms: float = 0.0
    last_error: Optional[str] = None
    exhausted: bool = False


class RetryService:
    """Reusable retry service with exponential backoff and jitter.

    Usage:
        retry_service = RetryService()
        result = await retry_service.execute(
            callable=my_async_func,
            args=("arg1",),
            kwargs={"key": "value"},
            policy=RetryPolicy(max_attempts=5),
        )
    """

    def __init__(self) -> None:
        self._metrics: dict[str, RetryMetrics] = {}

    async def execute(
        self,
        callable: Callable[..., Awaitable[T]],
        *,
        args: tuple = (),
        kwargs: dict[str, Any] = None,
        policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        operation_name: Optional[str] = None,
        on_retry: Optional[Callable[[RetryAttempt], Awaitable[None]]] = None,
        on_failure: Optional[Callable[[RetryAttempt], Awaitable[None]]] = None,
        on_success: Optional[Callable[[RetryAttempt], Awaitable[None]]] = None,
    ) -> T:
        """Execute a callable with retry logic.

        Args:
            callable: Async function to execute
            args: Positional arguments for the callable
            kwargs: Keyword arguments for the callable
            policy: Retry policy (defaults to RetryPolicy())
            circuit_breaker: Optional circuit breaker to check/record
            operation_name: Name for metrics tracking
            on_retry: Async callback on each retry attempt
            on_failure: Async callback on final failure
            on_success: Async callback on success

        Returns:
            Result of the callable

        Raises:
            Exception: The last exception if all attempts fail
        """
        kwargs = kwargs or {}
        policy = policy or RetryPolicy()
        operation_name = operation_name or getattr(callable, "__name__", "unknown")

        start_time = time.time()
        last_exc: Optional[Exception] = None
        last_status: Optional[int] = None

        for attempt in range(1, policy.max_attempts + 1):
            attempt_start = time.time()

            # Check circuit breaker before attempting
            if circuit_breaker is not None and not circuit_breaker.allow_request():
                logger.warning(
                    "Circuit breaker '%s' open, blocking request (attempt %d/%d)",
                    circuit_breaker.name,
                    attempt,
                    policy.max_attempts,
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{circuit_breaker.name}' is open"
                )

            try:
                result = await callable(*args, **kwargs)

                # Record success in circuit breaker
                if circuit_breaker is not None:
                    circuit_breaker.record_success()

                attempt_duration = (time.time() - attempt_start) * 1000
                attempt_info = RetryAttempt(
                    attempt_number=attempt,
                    delay_seconds=0.0,
                    duration_ms=attempt_duration,
                )

                if on_success:
                    await on_success(attempt_info)

                # Record metrics
                self._record_metrics(
                    operation_name,
                    total_attempts=attempt,
                    successful_attempt=attempt,
                    total_duration_ms=(time.time() - start_time) * 1000,
                    exhausted=False,
                )

                return result

            except CircuitBreakerOpenError:
                # Don't retry if circuit breaker is open - re-raise immediately
                raise

            except Exception as exc:
                last_exc = exc
                last_status = getattr(exc, "status_code", None)
                attempt_duration = (time.time() - attempt_start) * 1000

                # Record failure in circuit breaker
                if circuit_breaker is not None:
                    circuit_breaker.record_failure()

                # Determine if this should be retried
                decision = self._evaluate_retry(
                    exc=exc,
                    status_code=last_status,
                    attempt=attempt,
                    policy=policy,
                )

                attempt_info = RetryAttempt(
                    attempt_number=attempt,
                    delay_seconds=0.0,
                    error=exc,
                    status_code=last_status,
                    duration_ms=attempt_duration,
                )

                if decision == RetryDecision.FAIL_FAST:
                    logger.warning(
                        "Non-retryable error on attempt %d/%d for '%s': %s",
                        attempt,
                        policy.max_attempts,
                        operation_name,
                        exc,
                    )
                    if on_failure:
                        await on_failure(attempt_info)

                    self._record_metrics(
                        operation_name,
                        total_attempts=attempt,
                        successful_attempt=0,
                        total_duration_ms=(time.time() - start_time) * 1000,
                        last_error=str(exc),
                        exhausted=True,
                    )
                    raise

                if decision == RetryDecision.RETRY and attempt < policy.max_attempts:
                    delay = self._calculate_delay(attempt, policy)

                    attempt_info.delay_seconds = delay
                    logger.warning(
                        "Retrying '%s' in %.2fs (attempt %d/%d): %s",
                        operation_name,
                        delay,
                        attempt,
                        policy.max_attempts,
                        exc,
                    )

                    if on_retry:
                        await on_retry(attempt_info)

                    await asyncio.sleep(delay)
                    continue

                # All attempts exhausted
                logger.error(
                    "All %d attempts failed for '%s': %s",
                    policy.max_attempts,
                    operation_name,
                    exc,
                )
                if on_failure:
                    await on_failure(attempt_info)

                self._record_metrics(
                    operation_name,
                    total_attempts=attempt,
                    successful_attempt=0,
                    total_duration_ms=(time.time() - start_time) * 1000,
                    last_error=str(exc),
                    exhausted=True,
                )
                raise

        # Should not reach here, but just in case
        raise RuntimeError("Retry execution reached unreachable state")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_retry(
        self,
        exc: Exception,
        status_code: Optional[int],
        attempt: int,
        policy: RetryPolicy,
    ) -> RetryDecision:
        """Evaluate whether an attempt should be retried.

        Args:
            exc: The exception that occurred
            status_code: Optional HTTP status code
            attempt: Current attempt number (1-based)
            policy: Retry policy

        Returns:
            RetryDecision: RETRY, FAIL_FAST, or SUCCESS
        """
        # Check status codes first (for HTTP errors)
        if status_code is not None:
            if status_code in policy.retryable_status_codes:
                return RetryDecision.RETRY
            # Client errors (4xx) that aren't specifically retryable -> fail fast
            if 400 <= status_code < 500 and status_code != 429:
                return RetryDecision.FAIL_FAST

        # Check exception types
        if isinstance(exc, policy.retryable_exceptions):
            return RetryDecision.RETRY

        # Check common retryable error patterns via string matching
        exc_str = str(exc).lower()
        retryable_patterns = [
            "timeout",
            "timed out",
            "rate limit",
            "too many requests",
            "429",
            "503",
            "502",
            "connection",
            "reset",
            "temporarily",
            "try again",
        ]
        if any(pattern in exc_str for pattern in retryable_patterns):
            return RetryDecision.RETRY

        # Default: don't retry unknown errors
        return RetryDecision.FAIL_FAST

    def _calculate_delay(self, attempt: int, policy: RetryPolicy) -> float:
        """Calculate delay with exponential backoff and optional jitter.

        Args:
            attempt: Current attempt number (1-based)
            policy: Retry policy

        Returns:
            Delay in seconds
        """
        # Exponential backoff: base * 2^(attempt-1)
        delay = policy.base_delay * (2 ** (attempt - 1))

        # Apply max delay cap
        delay = min(delay, policy.max_delay)

        # Apply jitter
        if policy.use_jitter:
            jitter_range = delay * policy.jitter_factor
            jitter = jitter_range * (2 * random.random() - 1)
            delay += jitter

        return max(0.05, delay)

    def _record_metrics(
        self,
        operation_name: str,
        total_attempts: int,
        successful_attempt: int,
        total_duration_ms: float,
        last_error: Optional[str] = None,
        exhausted: bool = False,
    ) -> None:
        """Record metrics for an operation."""
        self._metrics[operation_name] = RetryMetrics(
            total_attempts=total_attempts,
            successful_attempt=successful_attempt,
            total_duration_ms=total_duration_ms,
            last_error=last_error,
            exhausted=exhausted,
        )

    def get_metrics(self, operation_name: Optional[str] = None) -> Any:
        """Get retry metrics.

        Args:
            operation_name: If provided, get metrics for specific operation.
                           If None, get all metrics.

        Returns:
            RetryMetrics or dict of operation_name -> RetryMetrics
        """
        if operation_name:
            return self._metrics.get(operation_name)
        return dict(self._metrics)

    def clear_metrics(self) -> None:
        """Clear all recorded metrics."""
        self._metrics.clear()


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker blocks a request."""
    pass