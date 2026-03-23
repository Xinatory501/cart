
from aiogram.filters import Filter
from aiogram.types import Message

from database.database import get_session
from database.repository import UserRepository

class BannedFilter(Filter):

    async def __call__(self, message: Message) -> bool:
        user_id = message.from_user.id

        async with get_session() as session:
            user_repo = UserRepository(session)
            return await user_repo.is_banned(user_id)
