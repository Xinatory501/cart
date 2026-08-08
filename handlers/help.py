from __future__ import annotations

import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.database import get_session
from database.repository import UserRepository
from locales.loader import get_text

logger = logging.getLogger(__name__)

router = Router()

@router.message(Command("help"))
async def help_command(message: Message):
    user_id = message.from_user.id
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        
        language = user.language if user else "ru"
        
    help_text = get_text("help_text", language)
    await message.answer(help_text)
