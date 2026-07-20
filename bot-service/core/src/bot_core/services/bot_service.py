"""Точка входа в бизнес-логику для обработки нормализованных сообщений."""

import logging
import re

from bot_core.config import settings
from bot_core.messages import (
    ANSWER_FAILED,
    DIALOG_RESET,
    FEEDBACK_ALREADY_RATED,
    FEEDBACK_DISLIKE,
    FEEDBACK_LIKE,
    GREETING,
    HELP_CONTACTS,
    SERVICE_UNAVAILABLE,
    SUBSCRIBED,
    SUBSCRIPTION_ERROR,
    UNSUPPORTED_FORMAT,
    UNKNOWN_COMMAND,
    VOICE_STUB,
)
from bot_core.models.callback import CallbackEvent
from bot_core.models.message import IncomingMessage
from bot_core.models.response import ActionType, BotResponse, InlineButton, KeyboardButton, OutgoingAction
from bot_core.services.agent_client import (
    AgentServiceClient,
    AgentServiceError,
    AgentServiceRateLimited,
    AgentServiceTimeout,
    AgentServiceUnavailable,
)
from bot_core.services.dialog_service import DialogService
from bot_core.services.feedback_service import FeedbackService, FEEDBACK_DISLIKE as FB_DISLIKE, FEEDBACK_LIKE as FB_LIKE
from bot_core.services.user_service import UserService

logger = logging.getLogger(__name__)


class BotService:
    """Обрабатывает нормализованные сообщения и возвращает платформенно-независимые действия."""

    def __init__(self) -> None:
        """Инициализирует зависимости бизнес-логики."""

        self._agent_client = AgentServiceClient(
            base_url=settings.agent_service_url,
            timeout_seconds=settings.agent_service_timeout_seconds,
        )
        self._dialog_service = DialogService()
        self._feedback_service = FeedbackService()
        self._user_service = UserService()

    async def close(self) -> None:
        """Закрывает HTTP-клиент."""

        await self._agent_client.close()

    def handle_message(self, message: IncomingMessage) -> BotResponse:
        """Обрабатывает сообщение и возвращает действия для адаптера платформы.

        Args:
            message: Нормализованное входящее сообщение от адаптера платформы.

        Returns:
            BotResponse: Действия, которые нужно выполнить на исходной платформе.
        """

        user = self._user_service.upsert_user(message)

        if message.message_type == "text":
            return self._handle_text_message(message, user)
        if message.message_type == "voice":
            return self._handle_voice_message(message)
        return self._build_unsupported_message_response(message)

    def handle_callback(self, event: CallbackEvent) -> BotResponse:
        """Обрабатывает callback-событие платформы.

        Args:
            event: Нормализованное callback-событие.

        Returns:
            BotResponse: Ответ для callback-события.
        """

        if event.callback_data in ("subscription:toggle", "menu:subscription"):
            user = self._user_service.toggle_subscription(event)
            if user is None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=SUBSCRIPTION_ERROR,
                        )
                    ]
                )

            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text=SUBSCRIBED if user.is_subscribed else UNSUBSCRIBED,
                        buttons=self._build_start_buttons(user.is_subscribed),
                    )
                ]
            )

        if event.callback_data == "menu:help":
            return self._build_help_response()

        if event.callback_data in ("dialog:start_new", "menu:new_dialog"):
            user = self._user_service.get_user(event.platform.value, event.user_id)
            if user is None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=SERVICE_UNAVAILABLE,
                        )
                    ]
                )

            dialog_session = self._dialog_service.start_new_dialog(user.id)
            if dialog_session is None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=SERVICE_UNAVAILABLE,
                        )
                    ]
                )

            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text=DIALOG_RESET,
                    )
                ]
            )

        if event.callback_data == "feedback:like":
            result = self._feedback_service.save_feedback(
                event.platform.value, event.user_id, FB_LIKE
            )
            if result == "already_rated":
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=FEEDBACK_ALREADY_RATED,
                        )
                    ]
                )
            if result is not None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=SERVICE_UNAVAILABLE,
                        )
                    ]
                )
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text=FEEDBACK_LIKE,
                    )
                ]
            )

        if event.callback_data == "feedback:dislike":
            result = self._feedback_service.save_feedback(
                event.platform.value, event.user_id, FB_DISLIKE
            )
            if result == "already_rated":
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=FEEDBACK_ALREADY_RATED,
                        )
                    ]
                )
            if result is not None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=SERVICE_UNAVAILABLE,
                        )
                    ]
                )
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text=FEEDBACK_DISLIKE,
                    )
                ]
            )

        return BotResponse(actions=[])

    def send_today_holiday_newsletter(self) -> dict[str, object]:
        """Запускает праздничную рассылку за текущую дату.

        Returns:
            dict[str, object]: Сводка по отправке.
        """

        # TODO: Implement holiday newsletter (requires holidays table)
        return {"holiday_name": None, "sent_count": 0, "skipped_count": 0, "failed_count": 0}

    def _handle_text_message(self, message: IncomingMessage, user) -> BotResponse:
        """Обрабатывает текстовое сообщение.

        Args:
            message: Нормализованное текстовое сообщение.
            user: Текущий пользователь из БД.

        Returns:
            BotResponse: Ответ для текстового сообщения.
        """

        normalized_text = (message.text or "").strip()
        lowered_text = normalized_text.lower()

        if lowered_text == "/start":
            return self._build_start_response(message, user)
        if lowered_text in ("/help", "📋 помощь"):
            return self._build_help_response()
        if lowered_text in ("🔄 новый диалог",):
            if user is not None:
                self._dialog_service.start_new_dialog(user.id)
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text=DIALOG_RESET,
                    )
                ]
            )
        if lowered_text in ("🔔 рассылка",):
            from bot_core.models.callback import CallbackEvent as CBEvent

            fake_event = CBEvent(
                platform=message.platform,
                user_id=message.user_id,
                chat_id=message.chat_id,
                callback_data="subscription:toggle",
            )
            toggled_user = self._user_service.toggle_subscription(fake_event)
            if toggled_user is not None:
                return BotResponse(
                    actions=[
                        OutgoingAction(
                            type=ActionType.send_text,
                            text=SUBSCRIBED if toggled_user.is_subscribed else UNSUBSCRIBED,
                        )
                    ]
                )
            return BotResponse(
                actions=[
                    OutgoingAction(
                        type=ActionType.send_text,
                        text=SUBSCRIPTION_ERROR,
                    )
                ]
            )
        if self._is_service_command(lowered_text):
            return self._build_service_command_response()

        reply_text, source_buttons = self._handle_dialog_message(normalized_text, user)

        feedback_buttons = self._build_feedback_buttons()

        all_buttons = feedback_buttons
        if source_buttons:
            all_buttons = source_buttons + all_buttons

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=reply_text,
                    buttons=all_buttons,
                )
            ]
        )

    def _handle_dialog_message(
        self, question: str, user
    ) -> tuple[str, list[list[InlineButton]]]:
        """Обрабатывает пользовательский вопрос с учетом истории диалога.

        Args:
            question: Текущий вопрос пользователя.
            user: Текущий пользователь из БД.

        Returns:
            Кортеж (текст ответа, inline-кнопки источников).
        """

        if user is None:
            agent_result = self._ask_agent_service(question)
            return self._format_agent_answer(agent_result)

        dialog_session = self._dialog_service.get_or_create_active_session(user.id)
        if dialog_session is None:
            agent_result = self._ask_agent_service(question)
            return self._format_agent_answer(agent_result)

        history = self._dialog_service.build_context(
            session_id=dialog_session.id,
        )
        agent_result = self._ask_agent_service(
            question=question,
            dialog_context=history,
        )
        self._dialog_service.save_question_answer(
            session_id=dialog_session.id,
            question=question,
            answer=agent_result.get("answer", ""),
            model_used=agent_result.get("model"),
            expanded_query=agent_result.get("expanded_query"),
            keywords=agent_result.get("keywords"),
            question_type=agent_result.get("intent"),
            relevance_type=agent_result.get("relevance_type"),
            relevant_sources=agent_result.get("relevant_sources"),
            source_links=agent_result.get("sources"),
        )
        return self._format_agent_answer(agent_result)

    def _handle_voice_message(self, message: IncomingMessage) -> BotResponse:
        """Обрабатывает голосовое сообщение.

        Args:
            message: Нормализованное голосовое сообщение.

        Returns:
            BotResponse: Заглушка до интеграции STT.
        """

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=VOICE_STUB,
                )
            ]
        )

    def _build_unsupported_message_response(
        self,
        message: IncomingMessage,
    ) -> BotResponse:
        """Возвращает ответ для неподдерживаемого типа сообщения.

        Args:
            message: Нормализованное входящее сообщение.

        Returns:
            BotResponse: Сообщение о неподдерживаемом формате.
        """

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=UNSUPPORTED_FORMAT,
                )
            ]
        )

    def _ask_agent_service(self, question: str, dialog_context: str | None = None) -> dict:
        """Отправляет вопрос в agent-service и возвращает полный ответ.

        Args:
            question: Вопрос пользователя.
            dialog_context: История диалога или другой дополнительный контекст.

        Returns:
            dict: Ответ с ключами answer, expanded_query, keywords, model,
            sources, intent, dialog_context, error.

        Raises:
            AgentServiceError: При ошибке запроса.
        """
        import asyncio
        from bot_core.services.agent_client import (
            AgentServiceError,
            AgentServiceRateLimited,
            AgentServiceTimeout,
            AgentServiceUnavailable,
        )

        async def _ask() -> dict:
            logger.info(
                "Sending to agent: question='%s', context_len=%d",
                question[:80],
                len(dialog_context or ""),
            )
            result = await self._agent_client.ask(
                question=question,
                dialog_context=dialog_context or "",
            )
            logger.info(
                "Agent response: answer_len=%d, intent=%s, sources=%d",
                len(result.get("answer", "")),
                result.get("intent"),
                len(result.get("sources", [])),
            )
            return result

        try:
            logger.info(
                "Sending to agent: question='%s', context_len=%d",
                question[:80],
                len(dialog_context or ""),
            )
            result = asyncio.run(_ask())
            logger.info(
                "Agent response: answer_len=%d, intent=%s, sources=%d",
                len(result.get("answer", "")),
                result.get("intent"),
                len(result.get("sources", [])),
            )
            return result
        except (AgentServiceTimeout, AgentServiceUnavailable, AgentServiceRateLimited, AgentServiceError) as e:
            logger.error("Agent service error: %s: %s", type(e).__name__, e)
            return {"answer": SERVICE_UNAVAILABLE}
        except Exception as e:
            logger.error("Unexpected agent error: %s", e)
            return {"answer": ANSWER_FAILED}

    def _format_agent_answer(
        self, agent_result: dict
    ) -> tuple[str, list[list[InlineButton]]]:
        """Форматирует ответ agent для отправки в мессенджер.

        Формирует inline-кнопки с URL из sources (SourceLink).
        Кнопки добавляются только если sources не пустой.

        Args:
            agent_result: Ответ от agent-service.

        Returns:
            Кортеж (отформатированный текст, inline-кнопки источников).
        """

        answer = agent_result.get("answer", "")
        sources = agent_result.get("sources", [])

        answer = self._strip_remaining_markdown(answer)

        source_buttons: list[list[InlineButton]] = []

        if sources:
            for src in sources[:3]:
                if isinstance(src, dict):
                    url = src.get("url", "")
                    label = src.get("label", "Подробнее")
                else:
                    url = str(src)
                    label = "Подробнее"
                if url:
                    source_buttons.append(
                        [InlineButton(text=label, url=url)]
                    )

        if len(answer) > 3900:
            answer = answer[:3850] + "\n\n..."

        return answer, source_buttons

    def _strip_remaining_markdown(self, text: str) -> str:
        """Удалить оставшийся markdown (safety-net после agent)."""
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _is_service_command(self, normalized_text: str) -> bool:
        """Определяет, является ли сообщение сервисной slash-командой.

        Args:
            normalized_text: Нормализованный текст сообщения.

        Returns:
            bool: `True`, если это сервисная команда.
        """

        return normalized_text.startswith("/")

    def _build_service_command_response(self) -> BotResponse:
        """Возвращает ответ для неподдерживаемой сервисной команды.

        Returns:
            BotResponse: Сервисный ответ без сохранения в историю.
        """

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=UNKNOWN_COMMAND,
                )
            ]
        )

    SOURCE_URL_BUTTONS: list[list[InlineButton]] = [
        [InlineButton(text="🌐 Официальный сайт ТюмГУ", url="https://utmn.ru")],
        [InlineButton(text="📄 Сведения об организации", url="https://sveden.utmn.ru")],
        [InlineButton(text="📖 Инструкции для ИС", url="https://confluence.utmn.ru/pages/viewpage.action?pageId=3607500")],
        [InlineButton(text="📚 Руководства для обучающихся", url="https://confluence.utmn.ru/pages/viewpage.action?pageId=86478972")],
    ]

    def _build_start_response(self, message: IncomingMessage, user) -> BotResponse:
        """Возвращает стартовое сообщение и базовые inline-кнопки.

        Args:
            message: Нормализованное входящее сообщение.
            user: Текущий пользователь из БД.

        Returns:
            BotResponse: Ответ для команды `/start`.
        """

        is_subscribed = bool(user.is_subscribed) if user is not None else False

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=GREETING,
                    buttons=self._build_start_buttons(is_subscribed),
                ),
            ]
        )

    def _build_help_response(self) -> BotResponse:
        """Возвращает справочное сообщение с контактами.

        Returns:
            BotResponse: Ответ для команды `/help`.
        """

        return BotResponse(
            actions=[
                OutgoingAction(
                    type=ActionType.send_text,
                    text=HELP_CONTACTS,
                    buttons=self.SOURCE_URL_BUTTONS,
                )
            ]
        )

    def _build_start_buttons(self, is_subscribed: bool) -> list[list[InlineButton]]:
        """Возвращает inline-кнопки стартового сообщения.

        Args:
            is_subscribed: Текущий статус подписки.

        Returns:
            list[list[InlineButton]]: Кнопки стартового сообщения.
        """

        subscription_text = (
            "Отписаться от рассылки" if is_subscribed else "Подписаться на рассылку"
        )

        return [
            [InlineButton(text="📋 Помощь", callback_data="menu:help")],
            [InlineButton(text="🔄 Новый диалог", callback_data="dialog:start_new")],
            [InlineButton(text="🔔 Рассылка", callback_data="subscription:toggle")],
        ]

    def _build_main_keyboard(self) -> list[list[KeyboardButton]]:
        """Возвращает постоянную reply-клавиатуру под полем ввода.

        Returns:
            list[list[KeyboardButton]]: Кнопки для быстрого доступа.
        """

        return [
            [KeyboardButton(text="📋 Помощь")],
            [KeyboardButton(text="🔄 Новый диалог")],
            [KeyboardButton(text="🔔 Рассылка")],
        ]

    def _build_feedback_buttons(self) -> list[list[InlineButton]]:
        """Возвращает inline-кнопки для оценки ответа.

        Returns:
            list[list[InlineButton]]: Кнопки лайка, дизлайка и нового диалога.
        """

        return [
            [
                InlineButton(text="❤️", callback_data="feedback:like"),
                InlineButton(text="👎", callback_data="feedback:dislike"),
            ],
        ]