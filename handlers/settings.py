from aiogram import Router, F
from aiogram.types import CallbackQuery

from config import settings
from database.database import get_session
from database.repository import UserRepository
from keyboards.language import get_language_keyboard
from keyboards.menu import get_main_menu_keyboard
from locales.loader import get_text

router = Router()

@router.callback_query(F.data == "settings_language")
async def change_language(callback: CallbackQuery):
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        language = user.language if user else settings.DEFAULT_LANGUAGE

    await callback.message.edit_caption(
        caption=get_text("select_language", language),
        reply_markup=get_language_keyboard(prefix="settings_lang"),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("settings_lang_"))
async def update_language(callback: CallbackQuery):
    language = callback.data.split("_")[-1]
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        await user_repo.update_language(user_id, language)

    await callback.message.edit_caption(
        caption=get_text("language_changed", language),
        reply_markup=get_main_menu_keyboard(language, has_history=True)
    )
    await callback.answer()
