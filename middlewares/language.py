
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from database.database import get_session
from database.repository import UserRepository
from config import settings

class LanguageMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if hasattr(event, 'from_user') and event.from_user:
            user_id = event.from_user.id

        if user_id:
            async with get_session() as session:
                user_repo = UserRepository(session)
                user = await user_repo.get_by_id(user_id)

                if user:
                    data['user_language'] = user.language
                else:
                    data['user_language'] = settings.DEFAULT_LANGUAGE
        else:
            data['user_language'] = settings.DEFAULT_LANGUAGE

        return await handler(event, data)
