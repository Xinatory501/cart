import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message

logger = logging.getLogger(__name__)

class DebugLoggerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        try:
            logger.info(
                "DEBUG_UPDATE: chat_id=%s chat_type=%s from_user_id=%s from_user_name=%s text=%r message_id=%s",
                event.chat.id if event.chat else None,
                event.chat.type if event.chat else None,
                event.from_user.id if event.from_user else None,
                event.from_user.username if event.from_user else None,
                event.text or event.caption or "[no text]",
                event.message_id
            )
        except Exception as error:
            logger.error("Failed to log debug update: %s", error)
        
        return await handler(event, data)
