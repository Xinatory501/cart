from pathlib import Path

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from database.database import get_session
from database.repository import ChatRepository, UserRepository, ConfigRepository
from keyboards.menu import get_main_menu_keyboard, get_persistent_reply_keyboard
from locales.loader import get_text
from services.bot_profile_service import get_default_language_for_bot

router = Router()
BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "cartame.jpg"


@router.message(F.text.lower() == "start")
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    default_language = get_default_language_for_bot(message.bot)
    has_history = False

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        user = await user_repo.get_by_id(user_id)

        if not user:
            user = await user_repo.create(user_id, username, first_name, last_name)
        await user_repo.update_language(user_id, default_language)
        language = default_language
        active_session = await chat_repo.get_active_session(user_id)
        if active_session:
            history = await chat_repo.get_session_history(active_session.id, limit=1)
            has_history = len(history) > 0

    greeting = get_text("greeting", language)

    welcome_sticker = None
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        welcome_sticker = await config_repo.get("welcome_sticker_file_id")

    if welcome_sticker:
        await message.answer_sticker(
            sticker=welcome_sticker,
            reply_markup=get_persistent_reply_keyboard(is_active=False, language=language)
        )
    else:
        await message.answer(
            "👋",
            reply_markup=get_persistent_reply_keyboard(is_active=False, language=language)
        )

    await message.answer_photo(
        photo=FSInputFile(BANNER_PATH),
        caption=greeting,
        reply_markup=get_main_menu_keyboard(language, has_history=has_history),
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

    welcome_sticker = None
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        welcome_sticker = await config_repo.get("welcome_sticker_file_id")

    try:
        await callback.message.delete()
    except Exception:
        pass

    if welcome_sticker:
        await callback.message.answer_sticker(
            sticker=welcome_sticker,
            reply_markup=get_persistent_reply_keyboard(is_active=False, language=language)
        )
    else:
        await callback.message.answer(
            "👋",
            reply_markup=get_persistent_reply_keyboard(is_active=False, language=language)
        )

    await callback.message.answer_photo(
        photo=FSInputFile(BANNER_PATH),
        caption=greeting,
        reply_markup=get_main_menu_keyboard(language, has_history=False),
    )
    await callback.answer()
