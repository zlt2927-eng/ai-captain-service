"""Unit tests for Circuit Breaker pattern."""

import time
from unittest.mock import patch

import pytest

from app.infrastructure.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerMetrics,
    CircuitBreakerRegistry,
    CircuitState,
)


class TestCircuitBreaker:
    """Test circuit breaker states and transitions."""

    def test_initial_state_closed(self):
        """Test initial state is CLOSED."""
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED

    def test_allow_request_when_closed(self):
        """Test requests are allowed when closed."""
        cb = CircuitBreaker(name="test")
        assert cb.allow_request() is True

    def test_open_after_consecutive_failures(self):
        """Test circuit opens after configured failure threshold."""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=60)

        # Allow first 2 requests
        assert cb.allow_request() is True
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        assert cb.allow_request() is True
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        # 3rd failure should open circuit
        assert cb.allow_request() is True
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_reject_requests_when_open(self):
        """Test requests are rejected when open."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=60)
        cb.record_failure()  # Opens circuit
        assert cb.state == CircuitState.OPEN

        assert cb.allow_request() is False

    def test_transition_to_half_open_after_timeout(self):
        """Test circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()  # Opens circuit
        assert cb.state == CircuitState.OPEN

        # Before timeout, requests rejected
        assert cb.allow_request() is False

        # After timeout, should transition to half-open
        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Test successful probe in half-open closes circuit."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()  # Opens

        time.sleep(0.05)
        assert cb.allow_request() is True  # Half-open probe
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        """Test failed probe in half-open reopens circuit."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()  # Opens

        time.sleep(0.05)
        assert cb.allow_request() is True  # Half-open probe
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_max_calls(self):
        """Test half-open limits probe calls."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=1,
            recovery_timeout=0.01,
            half_open_max_calls=2,
        )
        cb.record_failure()  # Opens

        time.sleep(0.05)
        # First probe allowed
        assert cb.allow_request() is True
        # Second probe allowed
        assert cb.allow_request() is True
        # Third probe rejected (max 2)
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        """Test successful call resets consecutive failures."""
        cb = CircuitBreaker(name="test", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # circuit should still be closed because success reset failures
        assert cb.state == CircuitState.CLOSED

    def test_reset(self):
        """Test manual reset."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=60)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_get_metrics(self):
        """Test metrics reporting."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.allow_request()
        cb.record_success()
        cb.allow_request()
        cb.record_success()
        cb.allow_request()
        cb.record_failure()

        metrics = cb.get_metrics()
        assert metrics.state == CircuitState.CLOSED
        assert metrics.success_count == 2
        assert metrics.failure_count == 1
        assert metrics.consecutive_failures == 1
        assert metrics.total_calls == 3

    def test_metrics_when_open(self):
        """Test metrics when circuit is open."""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=60)
        cb.record_failure()

        # Try a rejected request
        cb.allow_request()
        cb.allow_request()

        metrics = cb.get_metrics()
        assert metrics.state == CircuitState.OPEN
        assert metrics.rejected_calls >= 2
        assert metrics.consecutive_failures == 1


class TestCircuitBreakerRegistry:
    """Test circuit breaker registry."""

    def setup_method(self):
        """Reset singleton for each test."""
        CircuitBreakerRegistry._instance = None

    def test_singleton(self):
        """Test registry is a singleton."""
        registry1 = CircuitBreakerRegistry()
        registry2 = CircuitBreakerRegistry()
        assert registry1 is registry2

    def test_get_or_create(self):
        """Test get_or_create returns existing or new breaker."""
        registry = CircuitBreakerRegistry()
        cb1 = registry.get_or_create("test_service")
        cb2 = registry.get_or_create("test_service")
        assert cb1 is cb2  # Same instance

        cb3 = registry.get_or_create("other_service")
        assert cb3 is not cb1

    def test_get_nonexistent(self):
        """Test get returns None for nonexistent breaker."""
        registry = CircuitBreakerRegistry()
        assert registry.get("nonexistent") is None

    def test_get_all_metrics(self):
        """Test get_all_metrics returns all breakers."""
        registry = CircuitBreakerRegistry()
        registry.get_or_create("service_a")
        registry.get_or_create("service_b")

        metrics = registry.get_all_metrics()
        assert "service_a" in metrics
        assert "service_b" in metrics
        assert len(metrics) == 2

    def test_reset_all(self):
        """Test reset_all resets all breakers."""
        registry = CircuitBreakerRegistry()
        cb_a = registry.get_or_create("service_a", failure_threshold=1)
        cb_b = registry.get_or_create("service_b", failure_threshold=1)

        cb_a.record_failure()
        cb_b.record_failure()

        assert cb_a.state == CircuitState.OPEN
        assert cb_b.state == CircuitState.OPEN

        registry.reset_all()
        assert cb_a.state == CircuitState.CLOSED
        assert cb_b.state == CircuitState.CLOSED

    def test_reset_specific(self):
        """Test reset of specific breaker."""
        registry = CircuitBreakerRegistry()
        cb_a = registry.get_or_create("service_a", failure_threshold=1)
        registry.get_or_create("service_b", failure_threshold=1)

        cb_a.record_failure()
        assert cb_a.state == CircuitState.OPEN

        registry.reset("service_a")
        assert cb_a.state == CircuitState.CLOSED


class TestCircuitBreakerMetrics:
    """Test circuit breaker metrics dataclass."""

    def test_default_metrics(self):
        """Test default metrics values."""
        metrics = CircuitBreakerMetrics()
        assert metrics.state == CircuitState.CLOSED
        assert metrics.failure_count == 0
        assert metrics.success_count == 0
        assert metrics.consecutive_failures == 0
        assert metrics.open_duration_seconds == 0.0