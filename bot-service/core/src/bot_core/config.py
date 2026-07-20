"""Объекты конфигурации для bot-core."""

from dataclasses import dataclass
import os


def _parse_bool(value: str, default: bool = False) -> bool:
    """Преобразует строку окружения в булево значение."""

    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    """Настройки запуска bot-core."""

    app_name: str = os.getenv("BOT_CORE_APP_NAME", "bot-core")
    app_version: str = os.getenv("BOT_CORE_APP_VERSION", "0.1.0")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "voproshalych")
    postgres_user: str = os.getenv("POSTGRES_USER", "voproshalych")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "voproshalych")
    agent_service_url: str = os.getenv("AGENT_SERVICE_URL", "http://agent-service:8001")
    agent_service_timeout_seconds: float = float(
        os.getenv("AGENT_SERVICE_TIMEOUT_SECONDS", "300")
    )
    dialog_context_max_chars: int = int(
        os.getenv("DIALOG_CONTEXT_MAX_CHARS", "3000")
    )
    dialog_context_max_messages: int = int(
        os.getenv("DIALOG_CONTEXT_MAX_MESSAGES", "3")
    )
    holiday_newsletter_enabled: bool = _parse_bool(
        os.getenv("HOLIDAY_NEWSLETTER_ENABLED", "false"),
        default=False,
    )
    holiday_newsletter_run_hour: int = int(
        os.getenv("HOLIDAY_NEWSLETTER_RUN_HOUR", "9")
    )
    holiday_newsletter_run_minute: int = int(
        os.getenv("HOLIDAY_NEWSLETTER_RUN_MINUTE", "0")
    )


settings = Settings()