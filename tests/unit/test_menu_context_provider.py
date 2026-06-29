"""Unit tests for menu context provider.

Phase 6: Tests for Redis versioned cache, invalidation, warming.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.menu_context_provider import (
    MenuContextProvider,
    MockMenuContextProvider,
    LaravelMenuContextProvider,
    create_menu_context_provider,
    MENU_CACHE_TTL_SECONDS,
)
from app.core.config import Settings


class TestMockMenuContextProvider:
    """Test mock menu context provider."""

    @pytest.fixture
    def provider(self):
        """Provide mock menu provider."""
        return MockMenuContextProvider()

    @pytest.mark.asyncio
    async def test_get_menu_context(self, provider):
        """Test getting mock menu context."""
        menu = await provider.get_menu_context("rest_1")
        
        assert menu is not None
        assert "restaurant_id" in menu
        assert "categories" in menu
        assert len(menu["categories"]) > 0
        
        # Check structure
        category = menu["categories"][0]
        assert "id" in category
        assert "name" in category
        assert "dishes" in category
        
        # Check dish structure
        dish = category["dishes"][0]
        assert "id" in dish
        assert "name" in dish
        assert "price" in dish
        assert "external_price" in dish

    @pytest.mark.asyncio
    async def test_get_menu_context_returns_consistent_data(self, provider):
        """Test that mock menu returns consistent data."""
        menu1 = await provider.get_menu_context("rest_1")
        menu2 = await provider.get_menu_context("rest_1")
        
        assert menu1 == menu2

    @pytest.mark.asyncio
    async def test_get_menu_context_different_restaurants(self, provider):
        """Test mock menu for different restaurants."""
        menu1 = await provider.get_menu_context("rest_1")
        menu2 = await provider.get_menu_context("rest_2")
        
        # restaurant_id should differ
        assert menu1["restaurant_id"] == "rest_1"
        assert menu2["restaurant_id"] == "rest_2"
        # But all other data should be the same
        menu1_copy = dict(menu1)
        menu2_copy = dict(menu2)
        del menu1_copy["restaurant_id"]
        del menu2_copy["restaurant_id"]
        assert menu1_copy == menu2_copy


class TestLaravelMenuContextProvider:
    """Test Laravel menu context provider."""

    @pytest.fixture
    def mock_http_client(self):
        """Provide mock HTTP client."""
        mock = MagicMock()
        mock.get_json = AsyncMock()
        return mock

    @pytest.fixture
    def mock_redis_client(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.load_menu_cache = AsyncMock(return_value=None)
        mock.save_menu_cache = AsyncMock(return_value=None)
        mock.get_menu_cache_version = AsyncMock(return_value=1)
        mock.invalidate_menu_cache = AsyncMock(return_value=True)
        mock.warm_menu_cache = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def provider(self, mock_http_client, mock_redis_client, test_settings):
        """Provide Laravel menu provider with mocked dependencies."""
        return LaravelMenuContextProvider(
            mock_http_client,
            mock_redis_client,
            test_settings,
        )

    @pytest.mark.asyncio
    async def test_get_menu_context_from_backend(self, provider, mock_http_client, mock_redis_client):
        """Test fetching menu from Laravel backend."""
        mock_menu = {
            "restaurant_id": "rest_1",
            "categories": [
                {
                    "id": 10,
                    "name": "البرجر",
                    "dishes": [
                        {
                            "id": 101,
                            "name": "برجر لحم",
                            "price": 32.0,
                        }
                    ],
                }
            ],
        }
        mock_http_client.get_json.return_value = mock_menu
        
        menu = await provider.get_menu_context("rest_1")
        
        assert menu is not None
        assert menu["restaurant_id"] == "rest_1"
        mock_http_client.get_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_menu_context_adds_external_price(self, provider, mock_http_client, mock_redis_client):
        """Test that external_price is added if missing."""
        mock_menu = {
            "restaurant_id": "rest_1",
            "categories": [
                {
                    "id": 10,
                    "dishes": [
                        {
                            "id": 101,
                            "name": "برجر لحم",
                            "price": 32.0,
                            # No external_price
                        }
                    ],
                }
            ],
        }
        mock_http_client.get_json.return_value = mock_menu
        
        menu = await provider.get_menu_context("rest_1")
        
        dish = menu["categories"][0]["dishes"][0]
        assert "external_price" in dish
        assert dish["external_price"] == 32.0  # Should fallback to price

    @pytest.mark.asyncio
    async def test_get_menu_context_adds_rating_fields(self, provider, mock_http_client, mock_redis_client):
        """Test that rating fields are added if missing."""
        mock_menu = {
            "restaurant_id": "rest_1",
            "categories": [
                {
                    "id": 10,
                    "dishes": [
                        {
                            "id": 101,
                            "name": "برجر لحم",
                            "price": 32.0,
                        }
                    ],
                }
            ],
        }
        mock_http_client.get_json.return_value = mock_menu
        
        menu = await provider.get_menu_context("rest_1")
        
        dish = menu["categories"][0]["dishes"][0]
        assert "average_rating" in dish
        assert "review_count" in dish

    @pytest.mark.asyncio
    async def test_get_menu_context_caching(self, provider, mock_http_client, mock_redis_client):
        """Test menu caching behavior."""
        mock_menu = {
            "restaurant_id": "rest_1",
            "categories": [],
        }
        mock_http_client.get_json.return_value = mock_menu
        
        # First call - should fetch from backend
        await provider.get_menu_context("rest_1")
        assert mock_http_client.get_json.call_count == 1
        
        # Second call - should use in-memory cache
        await provider.get_menu_context("rest_1")
        # Should not call backend again (cached in memory)
        assert mock_http_client.get_json.call_count == 1

    @pytest.mark.asyncio
    async def test_get_menu_context_redis_cache_hit(self, provider, mock_http_client, mock_redis_client):
        """Test menu caching from Redis."""
        mock_menu_data = {
            "restaurant_id": "rest_1",
            "categories": [{"id": 10, "name": "البرجر", "dishes": []}],
        }
        mock_redis_client.load_menu_cache.return_value = mock_menu_data
        
        menu = await provider.get_menu_context("rest_1")
        
        assert menu == mock_menu_data
        # Should NOT call backend since Redis cache hit
        mock_http_client.get_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_menu_context_backend_failure_fallback(self, provider, mock_http_client, mock_redis_client):
        """Test fallback to mock on backend failure."""
        from app.infrastructure.http_client import HTTPClientError
        mock_http_client.get_json.side_effect = HTTPClientError("Backend down")
        
        # Should not raise, should fallback to mock
        menu = await provider.get_menu_context("rest_1")
        
        assert menu is not None
        assert "categories" in menu

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, provider, mock_redis_client):
        """Test cache invalidation."""
        # Add something to cache
        provider._cache["rest_1"] = {"test": "data"}
        provider._cache_timestamps["rest_1"] = 0
        
        await provider.invalidate_cache("rest_1")
        
        assert "rest_1" not in provider._cache
        assert "rest_1" not in provider._cache_timestamps
        # Should also invalidate Redis cache
        mock_redis_client.invalidate_menu_cache.assert_called_once_with("rest_1")

    @pytest.mark.asyncio
    async def test_clear_all_cache(self, provider, mock_redis_client):
        """Test clearing all cache."""
        provider._cache["rest_1"] = {"test": "data"}
        provider._cache["rest_2"] = {"test": "data2"}
        provider._cache_timestamps["rest_1"] = 0
        provider._cache_timestamps["rest_2"] = 0
        
        await provider.clear_all_cache()
        
        assert len(provider._cache) == 0
        assert len(provider._cache_timestamps) == 0

    @pytest.mark.asyncio
    async def test_warm_cache(self, provider, mock_http_client, mock_redis_client):
        """Test cache warming."""
        mock_menu = {"restaurant_id": "rest_1", "categories": []}
        mock_http_client.get_json.return_value = mock_menu
        
        await provider.warm_cache("rest_1")
        
        # Should have fetched and cached
        mock_http_client.get_json.assert_called_once()
        mock_redis_client.warm_menu_cache.assert_called_once()


class TestCreateMenuContextProvider:
    """Test menu context provider factory."""

    def test_create_mock_provider(self, test_settings):
        """Test creating mock provider."""
        provider = create_menu_context_provider(
            http_client=MagicMock(),
            redis_client=MagicMock(),
            settings=test_settings,
            use_mock=True,
        )
        
        assert isinstance(provider, MockMenuContextProvider)

    def test_create_laravel_provider(self, test_settings):
        """Test creating Laravel provider."""
        mock_http = MagicMock()
        mock_redis = MagicMock()
        
        provider = create_menu_context_provider(
            http_client=mock_http,
            redis_client=mock_redis,
            settings=test_settings,
            use_mock=False,
        )
        
        assert isinstance(provider, LaravelMenuContextProvider)

    def test_create_mock_when_no_backend_url(self, test_settings):
        """Test mock provider created when no backend URL."""
        test_settings.LARAVEL_BACKEND_URL = None
        
        provider = create_menu_context_provider(
            http_client=MagicMock(),
            redis_client=MagicMock(),
            settings=test_settings,
            use_mock=False,
        )
        
        assert isinstance(provider, MockMenuContextProvider)