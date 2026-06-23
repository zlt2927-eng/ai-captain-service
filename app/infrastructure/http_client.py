"""Reusable async HTTP client with retry logic."""

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class HTTPClientError(Exception):
    """Custom HTTP client error."""


class HTTPClient:
    """Async HTTP client wrapper with retries and structured error handling."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise HTTPClientError("HTTP client not connected")
        return self._client

    async def startup(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._settings.HTTP_TIMEOUT_SECONDS))
        logger.info("Initialized HTTP client")

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("Closed HTTP client")

    async def _sleep_backoff(self, attempt: int) -> None:
        delay = self._settings.HTTP_BACKOFF_BASE_SECONDS * (2 ** attempt)
        await asyncio.sleep(delay)

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        files: Optional[dict] = None,
        data: Optional[Any] = None,
    ) -> httpx.Response:
        client = await self._ensure_client()
        headers = dict(headers or {})

        for attempt in range(self._settings.HTTP_MAX_RETRIES):
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    files=files,
                    data=data,
                )
                if response.status_code >= 500 and attempt < self._settings.HTTP_MAX_RETRIES - 1:
                    logger.warning(
                        "HTTP %s %s returned %s, retrying (%s/%s)",
                        method,
                        url,
                        response.status_code,
                        attempt + 1,
                        self._settings.HTTP_MAX_RETRIES,
                    )
                    await self._sleep_backoff(attempt)
                    continue
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < self._settings.HTTP_MAX_RETRIES - 1:
                    logger.warning(
                        "HTTP %s %s failed with %s, retrying (%s/%s)",
                        method,
                        url,
                        type(exc).__name__,
                        attempt + 1,
                        self._settings.HTTP_MAX_RETRIES,
                    )
                    await self._sleep_backoff(attempt)
                    continue
                raise HTTPClientError(f"HTTP request failed: {exc}") from exc

        raise HTTPClientError(f"HTTP request exhausted retries: {method} {url}")

    async def post_json(self, url: str, json_data: dict, headers: Optional[dict] = None) -> dict:
        headers = dict(headers or {})
        headers.setdefault("Content-Type", "application/json")

        response = await self.request("POST", url, headers=headers, json_data=json_data)
        if response.status_code >= 400:
            raise HTTPClientError(
                f"POST {url} returned {response.status_code}: {response.text}"
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise HTTPClientError("Invalid JSON response from HTTP POST") from exc

    async def get_json(self, url: str, headers: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        response = await self.request("GET", url, headers=headers, params=params)
        if response.status_code >= 400:
            raise HTTPClientError(
                f"GET {url} returned {response.status_code}: {response.text}"
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise HTTPClientError("Invalid JSON response from HTTP GET") from exc

    async def stream(self, method: str, url: str, headers: Optional[dict] = None, json_data: Optional[dict] = None, data: Optional[Any] = None):
        client = await self._ensure_client()
        async with client.stream(method, url, headers=headers, json=json_data, data=data) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk
