"""Structured logging configuration."""

import logging
import sys
from typing import Optional


def setup_logging(log_level: str = "INFO", app_name: str = "ai-captain-service") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)
    logging.getLogger("google.generativeai").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class LogContext:
    """Context manager for structured logging with restaurant/session context."""

    def __init__(
        self,
        logger: logging.Logger,
        restaurant_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.logger = logger
        self.restaurant_id = restaurant_id
        self.session_id = session_id

    def _format_message(self, message: str) -> str:
        parts = [message]
        if self.restaurant_id:
            parts.append(f"[restaurant_id={self.restaurant_id}]")
        if self.session_id:
            parts.append(f"[session_id={self.session_id}]")
        return " ".join(parts)

    def info(self, message: str) -> None:
        self.logger.info(self._format_message(message))

    def warning(self, message: str) -> None:
        self.logger.warning(self._format_message(message))

    def error(self, message: str, exc_info: bool = False) -> None:
        self.logger.error(self._format_message(message), exc_info=exc_info)

    def debug(self, message: str) -> None:
        self.logger.debug(self._format_message(message))
