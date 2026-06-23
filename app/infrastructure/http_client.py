"""Reusable async HTTP client with retry logic and structured logging."""

import asyncio
import json
import logging
import time
from typing import Any, Optional

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class HTTPClientError(Exception):
    """Custom HTTP client error."""


class HTTPClient:
    """Async HTTP client wrapper with retries and structured error handling."""

    IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS"}

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None

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

    async def _sleep_backoff(self, attempt: int) -> None:
        """Exponential backoff with jitter for retry delays."""
        base_delay = self._settings.HTTP_BACKOFF_BASE_SECONDS
        delay = base_delay * (2 ** attempt)
        jitter = delay * 0.1 * (2 * (await asyncio.to_thread(__import__('random').random) - 0.5))
        sleep_for = max(0.1, delay + jitter)
        await asyncio.sleep(sleep_for)

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
        """Execute HTTP request with retry logic and structured logging.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            headers: Optional request headers
            params: Optional query parameters
            json_data: Optional JSON payload
            files: Optional multipart files
            data: Optional form data
            service_name: Target service name for logging
            endpoint_name: Endpoint name for logging
            correlation_id: Correlation ID for request tracing
            retry_on_server_error: Force retry on 5xx even for non-idempotent methods
            
        Returns:
            httpx.Response object
            
        Raises:
            HTTPClientError: If request fails after all retries
        """
        client = await self._ensure_client()
        headers = dict(headers or {})
        method_upper = method.upper()
        
        # Only retry 5xx for idempotent methods unless explicitly enabled
        retryable_server_error = retry_on_server_error or method_upper in self.IDEMPOTENT_METHODS

        for attempt in range(self._settings.HTTP_MAX_RETRIES):
            start_time = time.perf_counter()
            try:
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

                # Log successful request
                logger.info(
                    "HTTP request completed",
                    extra=self._log_fields(
                        method=method_upper,
                        url=url,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        service_name=service_name,
                        endpoint_name=endpoint_name,
                        correlation_id=correlation_id,
                        latency_ms=latency_ms,
                    ),
                )

                # Retry on server errors for idempotent methods
                if response.status_code >= 500 and retryable_server_error and attempt < self._settings.HTTP_MAX_RETRIES - 1:
                    logger.warning(
                        "HTTP request retrying due to server error",
                        extra=self._log_fields(
                            method=method_upper,
                            url=url,
                            status_code=response.status_code,
                            attempt=attempt + 1,
                            service_name=service_name,
                            endpoint_name=endpoint_name,
                            correlation_id=correlation_id,
                            latency_ms=latency_ms,
                        ),
                    )
                    await self._sleep_backoff(attempt)
                    continue
                    
                return response
                
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000
                if attempt < self._settings.HTTP_MAX_RETRIES - 1:
                    logger.warning(
                        "HTTP request transient failure, retrying",
                        extra=self._log_fields(
                            method=method_upper,
                            url=url,
                            attempt=attempt + 1,
                            service_name=service_name,
                            endpoint_name=endpoint_name,
                            correlation_id=correlation_id,
                            latency_ms=latency_ms,
                        ),
                        exc_info=exc,
                    )
                    await self._sleep_backoff(attempt)
                    continue
                raise HTTPClientError(f"HTTP request failed after {attempt + 1} attempts: {exc}") from exc
                
            except Exception as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    "HTTP request failed unexpectedly",
                    extra=self._log_fields(
                        method=method_upper,
                        url=url,
                        service_name=service_name,
                        endpoint_name=endpoint_name,
                        correlation_id=correlation_id,
                        latency_ms=latency_ms,
                    ),
                    exc_info=exc,
                )
                raise HTTPClientError(f"HTTP request failed: {exc}") from exc

        raise HTTPClientError(f"HTTP request exhausted retries: {method_upper} {url}")

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
            service_name: Target service name for logging
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
        
        if response.status_code >= 400:
            message = response.text
            raise HTTPClientError(
                f"POST {url} returned {response.status_code}: {message}"
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
            service_name: Target service name for logging
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
        
        if response.status_code >= 400:
            raise HTTPClientError(
                f"GET {url} returned {response.status_code}: {response.text}"
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
    ):
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