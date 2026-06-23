"""Menu context retrieval and caching for Gemini orchestrator."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

from app.infrastructure.http_client import HTTPClient
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
                            "currency": "SAR",
                            "ingredients": ["beef", "bun", "cheese"],
                            "allergens": ["gluten", "dairy"],
                            "calories": 650,
                            "preparation_time": 15,
                            "is_available": True,
                            "is_featured": True,
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
    
    Retrieves menu data from the Laravel backend API.
    """
    
    def __init__(self, http_client: HTTPClient, settings: Settings):
        self._http_client = http_client
        self._settings = settings
        self._cache: dict[str, dict] = {}
    
    async def get_menu_context(self, restaurant_id: str) -> dict:
        """Fetch menu context from Laravel backend.
        
        Args:
            restaurant_id: Restaurant identifier
            
        Returns:
            Menu context dictionary from backend
        """
        # Check cache first
        if restaurant_id in self._cache:
            logger.debug("Menu context cache hit", extra={"restaurant_id": restaurant_id})
            return self._cache[restaurant_id]
        
        # Fetch from backend
        url = f"{self._settings.LARAVEL_BACKEND_URL}/api/v1/restaurants/{restaurant_id}/menu"
        
        try:
            menu_data = await self._http_client.get_json(
                url,
                service_name="laravel_backend",
                endpoint_name="get_menu",
            )
            
            # Cache the result
            self._cache[restaurant_id] = menu_data
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
    settings: Settings,
    use_mock: bool = False,
) -> MenuContextProvider:
    """Factory function to create appropriate menu context provider.
    
    Args:
        http_client: HTTP client for backend calls
        settings: Application settings
        use_mock: Force use of mock provider (for development)
        
    Returns:
        MenuContextProvider instance
    """
    if use_mock or not settings.LARAVEL_BACKEND_URL:
        logger.info("Using mock menu context provider")
        return MockMenuContextProvider()
    
    logger.info("Using Laravel menu context provider")
    return LaravelMenuContextProvider(http_client, settings)