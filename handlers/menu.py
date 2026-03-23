from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import UserRepository, ChatRepository
from keyboards.menu import get_main_menu_keyboard, get_chat_keyboard
from keyboards.settings import get_settings_keyboard
from locales.loader import get_text
from states.user_states import UserStates

router = Router()

@router.callback_query(F.data == "menu_new_chat")
async def new_chat(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language

        await chat_repo.create_session(user_id)

    await callback.message.delete()
    await callback.message.answer(
        get_text("chat_started", language),
        reply_markup=get_chat_keyboard(language)
    )
    await state.set_state(UserStates.chatting)
    await callback.answer()

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

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language

        has_history = False
        active_session = await chat_repo.get_active_session(user_id)
        if active_session:
            history = await chat_repo.get_session_history(active_session.id, limit=1)
            has_history = len(history) > 0

    await callback.message.edit_caption(
        caption=get_text("greeting", language),
        reply_markup=get_main_menu_keyboard(language, has_history=has_history)
    )
    await callback.answer()
