"""Модели callback-событий от платформенных адаптеров."""

from typing import Any

from pydantic import BaseModel, Field

from bot_core.models.message import Platform


class CallbackEvent(BaseModel):
    """Нормализованное callback-событие от платформы.

    Attributes:
        platform: Идентификатор исходной платформы.
        user_id: Идентификатор пользователя на платформе.
        chat_id: Идентификатор чата на платформе.
        callback_data: Полезная нагрузка callback-кнопки.
        message_id: Идентификатор сообщения, к которому привязана кнопка.
        metadata: Дополнительные платформенно-специфичные поля.
    """

    platform: Platform
    user_id: str = Field(..., description="Идентификатор пользователя на платформе")
    chat_id: str = Field(..., description="Идентификатор чата на платформе")
    callback_data: str = Field(..., description="Полезная нагрузка callback-кнопки")
    message_id: str | None = Field(
        default=None,
        description="Идентификатор сообщения на платформе",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные поля платформы вне основного контракта core",
    )