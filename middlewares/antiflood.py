
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message

from database.database import get_session
from database.repository import FloodRepository, UserRepository, ConfigRepository
from config import settings

class AntiFloodMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if event.chat and event.chat.type != "private":
            return await handler(event, data)

        if not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id

        async with get_session() as session:
            flood_repo = FloodRepository(session)
            user_repo = UserRepository(session)
            config_repo = ConfigRepository(session)

            is_admin = user_id in settings.admin_ids or await user_repo.is_admin(user_id)
            if is_admin:
                return await handler(event, data)

            threshold = int(await config_repo.get("antiflood_threshold") or "1")
            time_window = int(await config_repo.get("antiflood_time_window") or "3")
            autoban_duration = int(await config_repo.get("autoban_duration") or "900")

            is_flooding, count = await flood_repo.check_and_update(
                user_id,
                threshold,
                time_window
            )

            if is_flooding:
                await user_repo.ban_user(user_id, autoban_duration)
                await flood_repo.increment_ban_count(user_id)

                ban_minutes = autoban_duration // 60
                await event.answer(
                    f"⚠️ Вы отправляете сообщения слишком часто.\n"
                    f"Вы временно заблокированы на {ban_minutes} минут."
                )
                return

        return await handler(event, data)
