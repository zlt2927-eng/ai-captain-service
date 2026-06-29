"""Reusable async HTTP client with circuit breaker and retry logic.

Uses RetryService for exponential backoff / jitter / retry policies and
CircuitBreaker for preventing cascading failures to external services.
"""

import json
import logging
import time
from typing import Any, AsyncIterator, Optional

import httpx

from app.core.config import Settings
from app.infrastructure.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
)
from app.infrastructure.retry_service import (
    CircuitBreakerOpenError,
    RetryPolicy,
    RetryService,
)

logger = logging.getLogger(__name__)


class HTTPClientError(Exception):
    """Custom HTTP client error."""


class HTTPStatusError(Exception):
    """HTTP status code error for triggering retry logic.

    Carries the status code so RetryService can evaluate retryability.
    """
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body[:200]}")


class HTTPClient:
    """Async HTTP client wrapper with circuit breaker and structured error handling.

    Uses RetryService for exponential backoff with jitter and configurable
    retry policies. Integrates CircuitBreaker for all external services
    to prevent cascading failures.
    """

    IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS"}

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None
        self._retry_service = RetryService()
        self._circuit_breakers = CircuitBreakerRegistry()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise HTTPClientError("HTTP client not connected")
        return self._client

    async def startup(self) -> None:
        """Initialize HTTP client with configured timeout."""
        timeout = httpx.Timeout(self._settings.HTTP_TIMEOUT_SECONDS)
        self._client = httpx.AsyncClient(timeout=timeout)
        logger.info(
            "Initialized HTTP client",
            extra={
                "timeout_seconds": self._settings.HTTP_TIMEOUT_SECONDS,
                "max_retries": self._settings.HTTP_MAX_RETRIES,
            },
        )

    async def shutdown(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("Closed HTTP client")

    def _log_fields(
        self,
        method: str,
        url: str,
        status_code: Optional[int] = None,
        attempt: Optional[int] = None,
        service_name: Optional[str] = None,
        endpoint_name: Optional[str] = None,
        correlation_id: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> dict[str, Any]:
        """Build structured log fields for HTTP requests."""
        fields: dict[str, Any] = {
            "method": method,
            "url": url,
            "status_code": status_code,
            "attempt": attempt,
        }
        if service_name:
            fields["service_name"] = service_name
        if endpoint_name:
            fields["endpoint_name"] = endpoint_name
        if correlation_id:
            fields["correlation_id"] = correlation_id
        if latency_ms is not None:
            fields["latency_ms"] = round(latency_ms, 2)
        return fields

    def _get_circuit_breaker(self, service_name: Optional[str]) -> Optional[CircuitBreaker]:
        """Get or create circuit breaker for a service."""
        if not service_name:
            return None
        return self._circuit_breakers.get_or_create(
            name=service_name,
            failure_threshold=self._settings.HTTP_MAX_RETRIES + 2,
            recovery_timeout=30.0,
            half_open_max_calls=3,
        )

    def _get_retry_policy(self, method_upper: str, retry_on_server_error: bool) -> RetryPolicy:
        """Get retry policy based on HTTP method and settings.

        Args:
            method_upper: Uppercase HTTP method
            retry_on_server_error: Force retry on 5xx for non-idempotent methods

        Returns:
            Configured RetryPolicy
        """
        retryable_server_error = retry_on_server_error or method_upper in self.IDEMPOTENT_METHODS

        if not retryable_server_error:
            # For non-idempotent writes, only retry on transient network errors
            return RetryPolicy(
                retryable_exceptions=(httpx.TimeoutException, httpx.NetworkError, ConnectionError, TimeoutError, OSError),
                retryable_status_codes={429},  # Only retry rate limits
                max_attempts=self._settings.HTTP_MAX_RETRIES,
                base_delay=self._settings.HTTP_BACKOFF_BASE_SECONDS,
            )

        return RetryPolicy(
            retryable_exceptions=(httpx.TimeoutException, httpx.NetworkError, ConnectionError, TimeoutError, OSError),
            retryable_status_codes={429, 500, 502, 503, 504},
            max_attempts=self._settings.HTTP_MAX_RETRIES,
            base_delay=self._settings.HTTP_BACKOFF_BASE_SECONDS,
        )

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        files: Optional[dict] = None,
        data: Optional[Any] = None,
        service_name: Optional[str] = None,
        endpoint_name: Optional[str] = None,
        correlation_id: Optional[str] = None,
        retry_on_server_error: bool = False,
    ) -> httpx.Response:
        """Execute HTTP request with circuit breaker and retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            headers: Optional request headers
            params: Optional query parameters
            json_data: Optional JSON payload
            files: Optional multipart files
            data: Optional form data
            service_name: Target service name for logging/metrics/circuit breaker
            endpoint_name: Endpoint name for logging
            correlation_id: Correlation ID for request tracing
            retry_on_server_error: Force retry on 5xx even for non-idempotent methods

        Returns:
            httpx.Response object

        Raises:
            HTTPClientError: If request fails after all retries or circuit is open
        """
        client = await self._ensure_client()
        headers = dict(headers or {})
        method_upper = method.upper()

        circuit_breaker = self._get_circuit_breaker(service_name)
        retry_policy = self._get_retry_policy(method_upper, retry_on_server_error)

        async def _make_request() -> httpx.Response:
            start_time = time.perf_counter()
            response = await client.request(
                method_upper,
                url,
                headers=headers,
                params=params,
                json=json_data,
                files=files,
                data=data,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "HTTP request completed",
                extra=self._log_fields(
                    method=method_upper,
                    url=url,
                    status_code=response.status_code,
                    attempt=None,  # Tracked by retry service
                    service_name=service_name,
                    endpoint_name=endpoint_name,
                    correlation_id=correlation_id,
                    latency_ms=latency_ms,
                ),
            )

            # Raise for status codes that should trigger retry or fail
            if response.status_code >= 400:
                raise HTTPStatusError(response.status_code, response.text)

            return response

        try:
            return await self._retry_service.execute(
                _make_request,
                operation_name=endpoint_name or f"{method_upper}_{url[:50]}",
                policy=retry_policy,
                circuit_breaker=circuit_breaker,
            )
        except CircuitBreakerOpenError as exc:
            raise HTTPClientError(f"Circuit breaker open: {exc}") from exc
        except HTTPStatusError as exc:
            raise HTTPClientError(
                f"{method_upper} {url} returned {exc.status_code}: {exc.body}"
            ) from exc
        except Exception as exc:
            if isinstance(exc, HTTPClientError):
                raise
            raise HTTPClientError(f"HTTP request failed: {exc}") from exc

    async def post_json(
        self,
        url: str,
        json_data: dict,
        headers: Optional[dict] = None,
        service_name: Optional[str] = None,
        endpoint_name: Optional[str] = None,
        correlation_id: Optional[str] = None,
        retry_on_server_error: bool = False,
    ) -> dict:
        """Send POST request with JSON payload.

        Args:
            url: Target URL
            json_data: JSON payload to send
            headers: Optional additional headers
            service_name: Target service name for logging/circuit breaker
            endpoint_name: Endpoint name for logging
            correlation_id: Correlation ID for request tracing
            retry_on_server_error: Force retry on 5xx errors

        Returns:
            Parsed JSON response

        Raises:
            HTTPClientError: If request fails or returns error status
        """
        headers = dict(headers or {})
        headers.setdefault("Content-Type", "application/json")

        response = await self.request(
            "POST",
            url,
            headers=headers,
            json_data=json_data,
            service_name=service_name,
            endpoint_name=endpoint_name,
            correlation_id=correlation_id,
            retry_on_server_error=retry_on_server_error,
        )

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise HTTPClientError("Invalid JSON response from HTTP POST") from exc

    async def get_json(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        service_name: Optional[str] = None,
        endpoint_name: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> dict:
        """Send GET request and parse JSON response.

        Args:
            url: Target URL
            headers: Optional additional headers
            params: Optional query parameters
            service_name: Target service name for logging/circuit breaker
            endpoint_name: Endpoint name for logging
            correlation_id: Correlation ID for request tracing

        Returns:
            Parsed JSON response

        Raises:
            HTTPClientError: If request fails or returns error status
        """
        response = await self.request(
            "GET",
            url,
            headers=headers,
            params=params,
            service_name=service_name,
            endpoint_name=endpoint_name,
            correlation_id=correlation_id,
            retry_on_server_error=True,  # GET is idempotent, safe to retry
        )

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise HTTPClientError("Invalid JSON response from HTTP GET") from exc

    async def stream(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        json_data: Optional[dict] = None,
        data: Optional[Any] = None,
    ) -> AsyncIterator[bytes]:
        """Stream HTTP response body as bytes.

        Args:
            method: HTTP method
            url: Target URL
            headers: Optional request headers
            json_data: Optional JSON payload
            data: Optional form data

        Yields:
            Response chunks as bytes
        """
        client = await self._ensure_client()
        async with client.stream(method, url, headers=headers, json=json_data, data=data) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk