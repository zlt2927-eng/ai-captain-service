"""Menu context retrieval and caching for Gemini orchestrator."""

import logging
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
    
    Retrieves menu data from the Laravel backend API with Redis caching.
    """
    
    def __init__(self, http_client: HTTPClient, redis_client: RedisClient, settings: Settings):
        self._http_client = http_client
        self._redis = redis_client
        self._settings = settings
        self._cache: dict[str, dict] = {}
    
    async def get_menu_context(self, restaurant_id: str) -> dict:
        """Fetch menu context from Laravel backend with caching.
        
        Args:
            restaurant_id: Restaurant identifier
            
        Returns:
            Menu context dictionary from backend
        """
        # Check in-memory cache first
        if restaurant_id in self._cache:
            logger.debug("Menu context memory cache hit", extra={"restaurant_id": restaurant_id})
            return self._cache[restaurant_id]
        
        # Check Redis cache
        redis_key = f"captain:menu:{restaurant_id}"
        try:
            cached = await self._redis.load_session_state(restaurant_id, "menu_cache")
            if cached and isinstance(cached, dict):
                menu_data = cached.get("menu")
                if menu_data:
                    logger.debug("Menu context Redis cache hit", extra={"restaurant_id": restaurant_id})
                    self._cache[restaurant_id] = menu_data
                    return menu_data
        except Exception as exc:
            logger.warning("Redis cache read failed", exc_info=True, extra={"restaurant_id": restaurant_id})
        
        # Fetch from backend
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
            
            # Cache in memory
            self._cache[restaurant_id] = menu_data
            
            # Cache in Redis with 5-minute TTL
            try:
                await self._redis.save_session_state(
                    restaurant_id,
                    "menu_cache",
                    {"menu": menu_data, "cached_at": __import__('time').time()},
                    300  # 5 minutes TTL
                )
            except Exception as exc:
                logger.warning("Redis cache write failed", exc_info=True, extra={"restaurant_id": restaurant_id})
            
            logger.info("Menu context fetched and cached", extra={"restaurant_id": restaurant_id})
            
            return menu_data
            
        except Exception as exc:
            logger.error("Failed to fetch menu context", exc_info=True, extra={"restaurant_id": restaurant_id})
            # Fallback to mock on error
            logger.warning("Falling back to mock menu context", extra={"restaurant_id": restaurant_id})
            mock_provider = MockMenuContextProvider()
            return await mock_provider.get_menu_context(restaurant_id)


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