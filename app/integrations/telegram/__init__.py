"""Telegram integration package.

This package provides optional Telegram bot integration.
The TelegramIntegration class is imported lazily to avoid
loading the telegram library when the feature is disabled.
"""

__all__ = ["TelegramIntegration"]


def __getattr__(name: str):
    """Lazy import of TelegramIntegration to avoid loading telegram library when disabled."""
    if name == "TelegramIntegration":
        from app.integrations.telegram.service import TelegramIntegration
        return TelegramIntegration
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")