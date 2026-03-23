
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from database.database import get_session
from database.repository import UserRepository

class AdminCheckMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id

        async with get_session() as session:
            user_repo = UserRepository(session)
            is_admin = await user_repo.is_admin(user_id)

            data['is_admin'] = is_admin

            if isinstance(event, Message) and event.text and event.text.startswith('/admin'):
                if not is_admin:
                    await event.answer("❌ У вас нет прав администратора.")
                    return

        return await handler(event, data)
