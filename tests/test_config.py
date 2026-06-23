import pytest

from app.core.config import get_settings, Settings


def test_get_settings_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_optional_telegram_validation_requires_token():
    # Required core secrets must still be provided
    with pytest.raises(ValueError):
        Settings(ENABLE_TELEGRAM=True, GEMINI_API_KEY="g", WEBSOCKET_AUTH_SECRET="s")


def test_optional_telegram_allowed_when_disabled():
    # Should construct fine when telegram disabled even without token
    s = Settings(ENABLE_TELEGRAM=False, GEMINI_API_KEY="g", WEBSOCKET_AUTH_SECRET="s")
    assert s.ENABLE_TELEGRAM is False
