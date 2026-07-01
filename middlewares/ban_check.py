
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message

from database.database import get_session
from database.repository import UserRepository
from locales.loader import get_text
from config import settings

class BanCheckMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id

        async with get_session() as session:
            user_repo = UserRepository(session)

            is_admin = user_id in settings.admin_ids or await user_repo.is_admin(user_id)
            if is_admin:
                return await handler(event, data)

            if await user_repo.is_banned(user_id):
                user = await user_repo.get_by_id(user_id)
                language = user.language if user else "en"
                await event.answer(get_text("banned", language))
                return

        return await handler(event, data)
