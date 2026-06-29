"""Menu context retrieval and caching for Gemini orchestrator.

Phase 6: Uses Redis versioned menu cache with invalidation and warming.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict

from app.infrastructure.http_client import HTTPClient
from app.infrastructure.redis_client import RedisClient
from app.core.config import Settings

logger = logging.getLogger(__name__)
class MenuContextProvider(ABC):
    """Abstract base class for menu context providers."""
    
    @abstractmethod
    async def get_menu_context(self, restaurant_id: str) -> dict:
        """Retrieve menu context for a restaurant.
        
        Args:
            restaurant_id: Restaurant identifier
            
        Returns:
            Menu context dictionary
        """
        pass


class MockMenuContextProvider(MenuContextProvider):
    """Mock menu context provider for development/testing.
    
    Returns hardcoded menu data. Preserves existing behavior.
    """
    
    async def get_menu_context(self, restaurant_id: str) -> dict:
        """Return mock menu context."""
        logger.debug("Using mock menu context", extra={"restaurant_id": restaurant_id})
        
        return {
            "restaurant_id": restaurant_id,
            "restaurant_name": "Captain Burger",
            "currency": "SAR",
            "language": "ar",
            "categories": [
                {
                    "id": 10,
                    "name": "البرجر",
                    "description": "برجر طازج",
                    "sort_order": 1,
                    "dishes": [
                        {
                            "id": 101,
                            "name": "برجر لحم",
                            "description": "برجر لحم مشوي مع صوص خاص",
                            "category_id": 10,
                            "price": 32.0,
                            "external_price": 32.0,
                            "currency": "SAR",
                            "ingredients": ["beef", "bun", "cheese"],
                            "allergens": ["gluten", "dairy"],
                            "calories": 650,
                            "preparation_time": 15,
                            "is_available": True,
                            "is_featured": True,
                            "average_rating": 4.5,
                            "review_count": 128,
                            "addons": [
                                {"id": 501, "name": "جبنة إضافية", "price": 4.0, "is_active": True},
                                {"id": 502, "name": "مشروم", "price": 3.0, "is_active": True},
                            ],
                        }
                    ],
                }
            ],
        }


class LaravelMenuContextProvider(MenuContextProvider):
    """Production menu context provider that fetches from Laravel backend.
    
    Phase 6: Uses Redis versioned menu cache with invalidation, warming, and metrics.
    Features:
    - In-memory cache with TTL for hot keys
    - Redis versioned cache with invalidation support
    - Cache warming on fetch
    - Fallback to mock data on backend failure
    - Removed duplicated cache logic (centralized in RedisClient)
    """
    
    def __init__(self, http_client: HTTPClient, redis_client: RedisClient, settings: Settings):
        self._http_client = http_client
        self._redis = redis_client
        self._settings = settings
        self._cache: dict[str, dict] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._cache_ttl_seconds: float = float(settings.DEFAULT_MENU_CACHE_TTL_SECONDS)
    
    async def get_menu_context(self, restaurant_id: str) -> dict:
        """Fetch menu context from Laravel backend with multi-level caching.
        
        Phase 6: Uses Redis versioned menu cache with invalidation.
        Cache hierarchy:
        1. In-memory cache (fastest)
        2. Redis versioned cache (distributed)
        3. Laravel backend (source of truth)
        4. Mock fallback (last resort)
        
        Args:
            restaurant_id: Restaurant identifier
            
        Returns:
            Menu context dictionary from backend
        """
        # 1. Check in-memory cache with TTL validation
        if self._is_memory_cache_valid(restaurant_id):
            logger.debug("Menu context memory cache hit", extra={"restaurant_id": restaurant_id})
            return self._cache[restaurant_id]
        
        # 2. Check Redis versioned cache
        try:
            menu_data = await self._redis.load_menu_cache(restaurant_id)
            if menu_data is not None:
                logger.debug("Menu context Redis cache hit", extra={"restaurant_id": restaurant_id})
                # Populate in-memory cache
                self._cache[restaurant_id] = menu_data
                self._cache_timestamps[restaurant_id] = time.time()
                return menu_data
        except Exception as exc:
            logger.warning("Redis cache read failed", exc_info=True, extra={"restaurant_id": restaurant_id})
        
        # 3. Fetch from backend
        url = f"{self._settings.LARAVEL_BACKEND_URL}/api/v1/restaurants/{restaurant_id}/menu"
        
        try:
            menu_data = await self._http_client.get_json(
                url,
                service_name="laravel_backend",
                endpoint_name="get_menu",
            )
            
            # Ensure external_price is present (fallback to price if not provided)
            if "categories" in menu_data:
                for category in menu_data["categories"]:
                    if "dishes" in category:
                        for dish in category["dishes"]:
                            if "external_price" not in dish:
                                dish["external_price"] = dish.get("price", 0.0)
                            # Add rating fields if not present
                            if "average_rating" not in dish:
                                dish["average_rating"] = None
                            if "review_count" not in dish:
                                dish["review_count"] = 0
            
            # Cache in memory with timestamp
            self._cache[restaurant_id] = menu_data
            self._cache_timestamps[restaurant_id] = time.time()
            
            # Cache in Redis with versioning (Phase 6)
            try:
                version = await self._redis.get_menu_cache_version(restaurant_id) or 1
                await self._redis.save_menu_cache(
                    restaurant_id,
                    menu_data,
                    ttl_seconds=self._settings.DEFAULT_MENU_CACHE_TTL_SECONDS,
                    version=version,
                )
            except Exception as exc:
                logger.warning("Redis cache write failed", exc_info=True, extra={"restaurant_id": restaurant_id})
            
            logger.info("Menu context fetched and cached", extra={"restaurant_id": restaurant_id})
            
            return menu_data
            
        except Exception as exc:
            logger.error("Failed to fetch menu context", exc_info=True, extra={"restaurant_id": restaurant_id})
            # 4. Fallback to mock on error
            logger.warning("Falling back to mock menu context", extra={"restaurant_id": restaurant_id})
            mock_provider = MockMenuContextProvider()
            return await mock_provider.get_menu_context(restaurant_id)
    
    def _is_memory_cache_valid(self, restaurant_id: str) -> bool:
        """Check if in-memory cache entry is still valid.
        
        Args:
            restaurant_id: Restaurant identifier
            
        Returns:
            True if cache is valid, False otherwise
        """
        if restaurant_id not in self._cache:
            return False
        
        cached_time = self._cache_timestamps.get(restaurant_id, 0)
        return (time.time() - cached_time) < self._cache_ttl_seconds
    
    async def invalidate_cache(self, restaurant_id: str) -> None:
        """Invalidate cache for a specific restaurant.
        
        Phase 6: Also invalidates Redis versioned cache.
        
        Args:
            restaurant_id: Restaurant identifier
        """
        self._cache.pop(restaurant_id, None)
        self._cache_timestamps.pop(restaurant_id, None)
        # Also invalidate Redis cache
        try:
            await self._redis.invalidate_menu_cache(restaurant_id)
        except Exception as exc:
            logger.warning("Redis cache invalidation failed", exc_info=True, extra={"restaurant_id": restaurant_id})
        logger.debug("Menu cache invalidated", extra={"restaurant_id": restaurant_id})
    
    async def clear_all_cache(self) -> None:
        """Clear all cached menu data."""
        for restaurant_id in list(self._cache.keys()):
            await self.invalidate_cache(restaurant_id)
        logger.info("Menu cache cleared")
    
    async def warm_cache(self, restaurant_id: str) -> None:
        """Pre-warm menu cache for a restaurant.
        
        Phase 6: Proactive cache warming.
        
        Args:
            restaurant_id: Restaurant identifier
        """
        try:
            menu_data = await self.get_menu_context(restaurant_id)
            await self._redis.warm_menu_cache(restaurant_id, menu_data, self._settings.DEFAULT_MENU_CACHE_TTL_SECONDS)
            logger.info("Menu cache warmed", extra={"restaurant_id": restaurant_id})
        except Exception as exc:
            logger.warning("Cache warming failed", exc_info=True, extra={"restaurant_id": restaurant_id})


def create_menu_context_provider(
    http_client: HTTPClient,
    redis_client: RedisClient,
    settings: Settings,
    use_mock: bool = False,
) -> MenuContextProvider:
    """Factory function to create appropriate menu context provider.
    
    Args:
        http_client: HTTP client for backend calls
        redis_client: Redis client for caching
        settings: Application settings
        use_mock: Force use of mock provider (for development)
        
    Returns:
        MenuContextProvider instance
    """
    if use_mock or not settings.LARAVEL_BACKEND_URL:
        logger.info("Using mock menu context provider")
        return MockMenuContextProvider()
    
    logger.info("Using Laravel menu context provider with Redis caching")
    return LaravelMenuContextProvider(http_client, redis_client, settings)