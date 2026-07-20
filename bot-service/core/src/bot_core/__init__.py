"""Инициализация пакета bot_core."""

from bot_core.config import settings
from bot_core.main import app, bot_service

__all__ = ["app", "bot_service", "settings"]