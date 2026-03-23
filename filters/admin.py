
from aiogram.filters import Filter
from aiogram.types import Message

from database.database import get_session
from database.repository import UserRepository
from config import settings

class AdminFilter(Filter):

    async def __call__(self, message: Message) -> bool:
        user_id = message.from_user.id

        if user_id in settings.admin_ids:
            return True

        async with get_session() as session:
            user_repo = UserRepository(session)
            return await user_repo.is_admin(user_id)
