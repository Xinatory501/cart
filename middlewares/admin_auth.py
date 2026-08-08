from __future__ import annotations
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from database.database import get_session
from database.repository import UserRepository
from config import settings

logger = logging.getLogger(__name__)

class AdminAuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Check only callback queries
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        callback_data = event.data or ""
        if not callback_data.startswith("admin_"):
            return await handler(event, data)

        user_id = event.from_user.id
        
        # Check if admin
        is_admin = user_id in settings.admin_ids
        
        if not is_admin:
            async with get_session() as session:
                user_repo = UserRepository(session)
                is_admin = await user_repo.is_admin(user_id)
                
        if not is_admin:
            logger.warning(f"Unauthorized admin access attempt: user={user_id} data={callback_data}")
            await event.answer("⛔ Доступ запрещён", show_alert=True)
            return
            
        return await handler(event, data)
