"""Unit tests for RetryService with exponential backoff, jitter, and policies."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.circuit_breaker import CircuitBreaker
from app.infrastructure.retry_service import (
    CircuitBreakerOpenError,
    RetryAttempt,
    RetryDecision,
    RetryMetrics,
    RetryPolicy,
    RetryService,
)


class TestRetryPolicy:
    """Test RetryPolicy dataclass."""

    def test_default_policy(self):
        """Test default policy values."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 30.0
        assert policy.use_jitter is True
        assert 429 in policy.retryable_status_codes

    def test_custom_policy(self):
        """Test custom policy values."""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=0.5,
            max_delay=10.0,
            jitter_factor=0.2,
            use_jitter=False,
        )
        assert policy.max_attempts == 5
        assert policy.base_delay == 0.5
        assert policy.use_jitter is False


class TestRetryService:
    """Test RetryService core functionality."""

    @pytest.fixture
    def retry_service(self):
        """Provide RetryService instance."""
        return RetryService()

    @pytest.mark.asyncio
    async def test_success_first_attempt(self, retry_service):
        """Test successful execution on first attempt."""
        mock_callable = AsyncMock(return_value="success")

        result = await retry_service.execute(
            mock_callable,
            policy=RetryPolicy(max_attempts=3),
        )

        assert result == "success"
        assert mock_callable.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self, retry_service):
        """Test retry after failure then succeed."""
        mock_callable = AsyncMock(side_effect=[TimeoutError("timeout"), "success"])

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            result = await retry_service.execute(
                mock_callable,
                policy=RetryPolicy(max_attempts=3, base_delay=0.01),
            )

        assert result == "success"
        assert mock_callable.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_exhausted(self, retry_service):
        """Test all retries exhausted raises exception."""
        mock_callable = AsyncMock(side_effect=TimeoutError("persistent timeout"))

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            with pytest.raises(TimeoutError):
                await retry_service.execute(
                    mock_callable,
                    policy=RetryPolicy(max_attempts=3, base_delay=0.01),
                )

        assert mock_callable.call_count == 3

    @pytest.mark.asyncio
    async def test_fail_fast_on_non_retryable(self, retry_service):
        """Test non-retryable exception fails fast."""
        mock_callable = AsyncMock(side_effect=ValueError("non-retryable"))

        with pytest.raises(ValueError):
            await retry_service.execute(
                mock_callable,
                policy=RetryPolicy(max_attempts=3),
            )

        assert mock_callable.call_count == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_open(self, retry_service):
        """Test circuit breaker open raises CircuitBreakerOpenError."""
        cb = CircuitBreaker(name="test_cb", failure_threshold=1, recovery_timeout=60)
        cb.record_failure()  # Opens circuit

        mock_callable = AsyncMock(return_value="success")

        with pytest.raises(CircuitBreakerOpenError):
            await retry_service.execute(
                mock_callable,
                policy=RetryPolicy(max_attempts=3),
                circuit_breaker=cb,
            )

        # Callable should not be called
        assert mock_callable.call_count == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_success(self, retry_service):
        """Test circuit breaker records success."""
        cb = CircuitBreaker(name="test_cb", failure_threshold=3)
        mock_callable = AsyncMock(return_value="success")

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            await retry_service.execute(
                mock_callable,
                policy=RetryPolicy(max_attempts=3),
                circuit_breaker=cb,
            )

        assert cb.state.name == "CLOSED"
        assert cb.get_metrics().success_count == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_failure(self, retry_service):
        """Test circuit breaker records failure."""
        cb = CircuitBreaker(name="test_cb", failure_threshold=3)
        mock_callable = AsyncMock(side_effect=TimeoutError("fail"))

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            with pytest.raises(TimeoutError):
                await retry_service.execute(
                    mock_callable,
                    policy=RetryPolicy(max_attempts=3, base_delay=0.01),
                    circuit_breaker=cb,
                )

        assert cb.get_metrics().failure_count == 3

    @pytest.mark.asyncio
    async def test_retry_status_code_500(self, retry_service):
        """Test retry on HTTP 500 status."""
        class HTTPError(Exception):
            def __init__(self, status_code):
                self.status_code = status_code
                super().__init__(f"HTTP {status_code}")

        mock_callable = AsyncMock(side_effect=[
            HTTPError(500),
            "success",
        ])

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            result = await retry_service.execute(
                mock_callable,
                policy=RetryPolicy(max_attempts=3, base_delay=0.01),
            )

        assert result == "success"
        assert mock_callable.call_count == 2

    @pytest.mark.asyncio
    async def test_fail_fast_on_400_status(self, retry_service):
        """Test fail fast on 4xx status codes (except 429)."""
        class HTTPError(Exception):
            def __init__(self, status_code):
                self.status_code = status_code
                super().__init__(f"HTTP {status_code}")

        mock_callable = AsyncMock(side_effect=HTTPError(404))

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            with pytest.raises(HTTPError):
                await retry_service.execute(
                    mock_callable,
                    policy=RetryPolicy(max_attempts=3),
                )

        assert mock_callable.call_count == 1

    @pytest.mark.asyncio
    async def test_on_retry_callback(self, retry_service):
        """Test on_retry callback is called."""
        callback = AsyncMock()
        mock_callable = AsyncMock(side_effect=[TimeoutError("fail"), "success"])

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            await retry_service.execute(
                mock_callable,
                policy=RetryPolicy(max_attempts=3, base_delay=0.01),
                on_retry=callback,
            )

        callback.assert_called_once()
        assert isinstance(callback.call_args[0][0], RetryAttempt)

    @pytest.mark.asyncio
    async def test_on_success_callback(self, retry_service):
        """Test on_success callback is called."""
        callback = AsyncMock()
        mock_callable = AsyncMock(return_value="success")

        await retry_service.execute(
            mock_callable,
            policy=RetryPolicy(max_attempts=3),
            on_success=callback,
        )

        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_failure_callback(self, retry_service):
        """Test on_failure callback is called after exhaustion."""
        callback = AsyncMock()
        mock_callable = AsyncMock(side_effect=TimeoutError("fail"))

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            with pytest.raises(TimeoutError):
                await retry_service.execute(
                    mock_callable,
                    policy=RetryPolicy(max_attempts=2, base_delay=0.01),
                    on_failure=callback,
                )

        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_operation_name_metrics(self, retry_service):
        """Test metrics tracked by operation name."""
        mock_callable = AsyncMock(return_value="success")

        await retry_service.execute(
            mock_callable,
            operation_name="my_operation",
            policy=RetryPolicy(max_attempts=3),
        )

        metrics = retry_service.get_metrics("my_operation")
        assert metrics is not None
        assert metrics.total_attempts == 1
        assert metrics.successful_attempt == 1
        assert metrics.exhausted is False

    @pytest.mark.asyncio
    async def test_get_all_metrics(self, retry_service):
        """Test get_metrics returns all when name not given."""
        mock_callable = AsyncMock(return_value="success")

        await retry_service.execute(mock_callable, operation_name="op_a")
        await retry_service.execute(mock_callable, operation_name="op_b")

        all_metrics = retry_service.get_metrics()
        assert "op_a" in all_metrics
        assert "op_b" in all_metrics

    def test_clear_metrics(self, retry_service):
        """Test clear_metrics removes all metrics."""
        retry_service._metrics["test"] = RetryMetrics(total_attempts=1)
        assert len(retry_service.get_metrics()) == 1

        retry_service.clear_metrics()
        assert len(retry_service.get_metrics()) == 0

    def test_calculate_delay(self, retry_service):
        """Test delay calculation."""
        policy = RetryPolicy(base_delay=1.0, max_delay=10.0, use_jitter=False)

        delay_1 = retry_service._calculate_delay(1, policy)
        assert delay_1 == 1.0  # base * 2^0 = 1

        delay_2 = retry_service._calculate_delay(2, policy)
        assert delay_2 == 2.0  # base * 2^1 = 2

        delay_3 = retry_service._calculate_delay(3, policy)
        assert delay_3 == 4.0  # base * 2^2 = 4

    def test_calculate_delay_with_jitter(self, retry_service):
        """Test delay with jitter."""
        policy = RetryPolicy(base_delay=1.0, max_delay=10.0, use_jitter=True)

        with patch("app.infrastructure.retry_service.random.random", return_value=0.5):
            delay = retry_service._calculate_delay(1, policy)
            # base * 2^0 = 1, jitter = 1 * 0.1 * (2*0.5 - 1) = 0
            assert delay == 1.0

    def test_calculate_delay_max_cap(self, retry_service):
        """Test delay is capped at max_delay."""
        policy = RetryPolicy(base_delay=10.0, max_delay=15.0, use_jitter=False)

        delay = retry_service._calculate_delay(3, policy)
        # base * 2^2 = 40, capped at 15
        assert delay == 15.0

    def test_calculate_delay_min(self, retry_service):
        """Test minimum delay."""
        policy = RetryPolicy(base_delay=0.01, max_delay=10.0, use_jitter=False)

        delay = retry_service._calculate_delay(1, policy)
        assert delay == 0.05  # max(0.05, 0.01)


class TestRetryDecision:
    """Test retry decision evaluation."""

    def test_retryable_exception(self):
        """Test retryable exception returns RETRY."""
        service = RetryService()
        policy = RetryPolicy(retryable_exceptions=(TimeoutError,))

        decision = service._evaluate_retry(
            exc=TimeoutError("timeout"),
            status_code=None,
            attempt=1,
            policy=policy,
        )
        assert decision == RetryDecision.RETRY

    def test_non_retryable_exception(self):
        """Test non-retryable exception returns FAIL_FAST."""
        service = RetryService()
        policy = RetryPolicy()

        decision = service._evaluate_retry(
            exc=ValueError("bad value"),
            status_code=None,
            attempt=1,
            policy=policy,
        )
        assert decision == RetryDecision.FAIL_FAST

    def test_retryable_status_code(self):
        """Test retryable status code returns RETRY."""
        service = RetryService()
        policy = RetryPolicy(retryable_status_codes={500, 503})

        decision = service._evaluate_retry(
            exc=Exception("Server Error"),
            status_code=500,
            attempt=1,
            policy=policy,
        )
        assert decision == RetryDecision.RETRY

    def test_non_retryable_status_code(self):
        """Test non-retryable status code returns FAIL_FAST."""
        service = RetryService()
        policy = RetryPolicy()

        decision = service._evaluate_retry(
            exc=Exception("Not Found"),
            status_code=404,
            attempt=1,
            policy=policy,
        )
        assert decision == RetryDecision.FAIL_FAST

    def test_retry_on_rate_limit_string(self):
        """Test retry on rate limit error message."""
        service = RetryService()
        policy = RetryPolicy()

        decision = service._evaluate_retry(
            exc=Exception("rate limit exceeded"),
            status_code=None,
            attempt=1,
            policy=policy,
        )
        assert decision == RetryDecision.RETRY