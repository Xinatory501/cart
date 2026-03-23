from pathlib import Path

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from database.database import get_session
from database.repository import UserRepository
from keyboards.menu import get_main_menu_keyboard
from locales.loader import get_text
from services.bot_profile_service import get_default_language_for_bot, set_user_bot_key
from services.thread_service import ThreadService

router = Router()
BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "cartame.jpg"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    default_language = get_default_language_for_bot(message.bot)

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)

        if not user:
            user = await user_repo.create(user_id, username, first_name, last_name)
        await user_repo.update_language(user_id, default_language)
        language = default_language

    thread_service = ThreadService(message.bot)
    await thread_service.ensure_thread_for_user(
        user_id=user_id,
        username=username,
        first_name=first_name,
    )

    await set_user_bot_key(user_id, thread_service.profile.key)

    greeting = get_text("greeting", language)

    await message.answer_photo(
        photo=FSInputFile(BANNER_PATH),
        caption=greeting,
        reply_markup=get_main_menu_keyboard(language, has_history=True),
    )


@router.callback_query(F.data.startswith("lang_"))
async def choose_language(callback: CallbackQuery, state: FSMContext):
    del state
    language = callback.data.split("_")[1]
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            user = await user_repo.create(
                user_id,
                callback.from_user.username,
                callback.from_user.first_name,
                callback.from_user.last_name,
            )
        await user_repo.update_language(user_id, language)

    greeting = get_text("greeting", language)

    await callback.message.edit_caption(
        caption=greeting,
        reply_markup=get_main_menu_keyboard(language, has_history=False),
    )
    await callback.answer()
