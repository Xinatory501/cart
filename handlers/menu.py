import asyncio

from pathlib import Path
from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import UserRepository, ChatRepository, ConfigRepository
from keyboards.menu import get_main_menu_keyboard, get_chat_keyboard, get_persistent_reply_keyboard
from keyboards.settings import get_settings_keyboard
from locales.loader import get_text
from services.bot_profile_service import set_user_bot_key
from services.thread_service import ThreadService
from states.user_states import UserStates

router = Router()
BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "cartame.jpg"


async def _prepare_support_thread_for_new_chat(
    callback: CallbackQuery,
    user_id: int,
) -> None:
    thread_service = ThreadService(callback.bot)
    thread_id_before = await thread_service.get_thread_id_for_user(user_id)

    ticket_number = await thread_service.issue_new_ticket_number(user_id)
    thread_id = await thread_service.ensure_thread_for_user(
        user_id=user_id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    await set_user_bot_key(user_id, thread_service.profile.key)

    if ticket_number:
        ticket_message = await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text=(
                "Новый чат создан.\n"
                "Ваш номер обращения:\n"
                f"<code>{ticket_number}</code>\n\n"
                "Сохраните его, чтобы быстро передать поддержке."
            ),
            parse_mode="HTML",
        )
        try:
            await callback.bot.pin_chat_message(
                chat_id=callback.message.chat.id,
                message_id=ticket_message.message_id,
                disable_notification=True,
            )
        except Exception:
            pass

    target_thread_id = thread_id_before or thread_id
    if target_thread_id and ticket_number:
        try:
            await callback.bot.send_message(
                chat_id=thread_service.support_group_id,
                message_thread_id=target_thread_id,
                text=(
                    "<b>Система:</b>\n"
                    "Пользователь начал новый чат.\n"
                    f"Номер чата: <code>{ticket_number}</code>"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.callback_query(F.data == "menu_new_chat")
async def new_chat(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language

        await chat_repo.create_session(user_id)

    await callback.answer()

    await callback.message.delete()
    await callback.message.answer(
        get_text("chat_started", language),
        reply_markup=get_chat_keyboard(language)
    )
    await callback.message.answer(
        get_text("get_ticket_number_hint", language),
        reply_markup=get_persistent_reply_keyboard(is_active=True, language=language)
    )
    await state.set_state(UserStates.chatting)

    asyncio.create_task(
        _prepare_support_thread_for_new_chat(
            callback=callback,
            user_id=user_id,
        )
    )

@router.callback_query(F.data == "menu_continue_chat")
async def continue_chat(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language

        await chat_repo.activate_ai(user_id)

    await callback.message.delete()
    await callback.message.answer(
        get_text("chat_continued", language),
        reply_markup=get_chat_keyboard(language)
    )
    await callback.message.answer(
        get_text("get_ticket_number_hint", language),
        reply_markup=get_persistent_reply_keyboard(is_active=True, language=language)
    )
    await state.set_state(UserStates.chatting)
    await callback.answer()

@router.callback_query(F.data == "menu_settings")
async def open_settings(callback: CallbackQuery):
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        language = user.language

    await callback.message.edit_caption(
        caption=get_text("settings", language),
        reply_markup=get_settings_keyboard(language)
    )
    await callback.answer()

@router.callback_query(F.data == "menu_back")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    await state.clear()

    welcome_sticker = None
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        config_repo = ConfigRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language
        welcome_sticker = await config_repo.get("welcome_sticker_file_id")

        has_history = False
        active_session = await chat_repo.get_active_session(user_id)
        if active_session:
            history = await chat_repo.get_session_history(active_session.id, limit=1)
            has_history = len(history) > 0

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
        caption=get_text("greeting", language),
        reply_markup=get_main_menu_keyboard(language, has_history=has_history)
    )
    await callback.answer()
