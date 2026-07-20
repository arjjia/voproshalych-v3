"""Клиент для обращения к agent-service."""

import logging
import uuid

import httpx


logger = logging.getLogger(__name__)


class AgentServiceError(Exception):
    """Базовый класс для ошибок agent-service."""

    pass


class AgentServiceTimeout(AgentServiceError):
    """Превышен таймаут."""

    pass


class AgentServiceUnavailable(AgentServiceError):
    """Agent-service недоступен."""

    pass


class AgentServiceRateLimited(AgentServiceError):
    """Agent-service временно ограничивает запросы."""

    pass


class AgentServiceClient:
    """Асинхронный HTTP-клиент для agent-service.

    Для неидемпотентных POST-запросов не использует автоматические ретраи:
    один вызов клиента соответствует одной попытке обращения к agent-service.
    """

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        """Инициализирует клиента agent-service.

        Args:
            base_url: Базовый URL agent-service.
            timeout_seconds: Таймаут запросов в секундах.
        """

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        """Закрывает HTTP-клиент."""

        await self._client.aclose()

    async def ask(
        self,
        question: str,
        user_id: str = "anonymous",
        role: str = "guest",
        dialog_context: str = "",
    ) -> dict:
        """Отправляет вопрос в agent-service одной попыткой.

        Args:
            question: Вопрос пользователя.
            user_id: Идентификатор пользователя.
            role: Роль пользователя.
            dialog_context: Дополнительный контекст диалога.

        Returns:
            dict: Ответ agent-service с ключами:
                - answer: str — текст ответа
                - sources: list[dict] — источники для кнопок ({url, label})
                - intent: str — тип намерения
                - dialog_context: str — обновленный контекст диалога
                - error: str | None — ошибка, если есть

        Raises:
            AgentServiceError: При ошибке запроса.
        """
        request_id = uuid.uuid4().hex[:8]
        headers = {"X-Request-ID": request_id}
        payload = {
            "query": question,
            "user_id": user_id,
            "role": role,
            "dialog_context": dialog_context,
        }
        logger.info(
            "Sending to agent-service: question='%s', user_id=%s, role=%s, context_len=%d",
            question[:80],
            user_id,
            role,
            len(dialog_context or ""),
        )
        try:
            response = await self._client.post(
                "/chat",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            payload_data = response.json()
            logger.info(
                "Agent response: answer_len=%d, intent=%s, sources=%d, error=%s",
                len(payload_data.get("answer", "")),
                payload_data.get("intent"),
                len(payload_data.get("sources") or []),
                payload_data.get("error"),
            )
            return {
                "answer": payload_data.get("answer", ""),
                "sources": payload_data.get("sources", []),
                "intent": payload_data.get("intent"),
                "dialog_context": payload_data.get("dialog_context", ""),
                "error": payload_data.get("error"),
            }
        except httpx.TimeoutException as exc:
            logger.warning("Agent service timeout")
            raise AgentServiceTimeout("Agent service timeout") from exc
        except httpx.ConnectError as exc:
            logger.warning("Cannot connect to agent service")
            raise AgentServiceUnavailable("Cannot connect to agent service") from exc
        except httpx.HTTPStatusError as exc:
            raise self._map_http_error(exc) from exc
        except Exception as exc:
            logger.error("Unexpected error: %s: %s", type(exc).__name__, exc)
            raise AgentServiceError(f"Unexpected error: {str(exc)}") from exc

    def _map_http_error(self, exc: httpx.HTTPStatusError) -> AgentServiceError:
        """Преобразовать HTTP-ошибку agent-service в доменное исключение."""
        status_code = exc.response.status_code
        response_snippet = exc.response.text[:200]

        if status_code == 429:
            logger.warning("Agent service rate limited")
            return AgentServiceRateLimited("Agent service rate limited")

        if status_code in (503, 504):
            logger.warning("Agent service unavailable")
            return AgentServiceUnavailable("Agent service is unavailable")

        if status_code in (400, 422):
            logger.error("Agent service invalid request")
            return AgentServiceError(f"Invalid request: {response_snippet}")

        if status_code >= 500:
            logger.error(
                "Agent service HTTP error %s",
                status_code,
            )
            return AgentServiceError(f"Agent service error: {status_code}")

        logger.error(
            "Agent service unexpected HTTP error %s",
            status_code,
        )
        return AgentServiceError(f"Agent service HTTP error: {status_code}")