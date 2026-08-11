import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import UserRepository, ChatRepository
from keyboards.menu import get_main_menu_keyboard, get_chat_keyboard, get_csat_keyboard
from keyboards.settings import get_settings_keyboard
from locales.loader import get_text
from states.user_states import UserStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "menu_new_chat")
async def new_chat(callback: CallbackQuery, state: FSMContext):
    """Создаёт новый кейс с уникальным тикетом и отправляет сообщение с кодом."""
    user_id = callback.from_user.id

    from services.thread_service import ThreadService
    thread_service = ThreadService(callback.bot)
    existing_thread_id = await thread_service.get_thread_id_for_user(user_id)

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "ru"

        # Создаём новый кейс — внутри генерируется тикет и передаётся support_thread_id
        new_session = await chat_repo.create_session(user_id, channel="telegram", support_thread_id=existing_thread_id)
        ticket_code = new_session.ticket_code or "??????"

    try:
        await thread_service.rename_thread_for_case(user_id, ticket_code, "NEW")
    except Exception:
        pass

    await callback.message.delete()

    # Сообщение о начале нового обращения с кодом тикета
    ticket_message = await callback.message.answer(
        get_text("new_case_started", language).format(ticket=ticket_code),
        parse_mode="HTML",
        reply_markup=get_chat_keyboard(language, ticket_code),
    )

    # Закрепляем сообщение с тикетом в чате
    try:
        await callback.bot.pin_chat_message(
            chat_id=callback.message.chat.id,
            message_id=ticket_message.message_id,
            disable_notification=True,
        )
        # Сохраняем ID закреплённого сообщения
        async with get_session() as session:
            chat_repo = ChatRepository(session)
            active = await chat_repo.get_active_session(user_id)
            if active:
                await chat_repo.set_pinned_message_id(active.id, ticket_message.message_id)
    except Exception as e:
        logger.warning("Не удалось закрепить сообщение с тикетом: %s", e)

    await state.set_state(UserStates.chatting)
    await callback.answer()


@router.callback_query(F.data == "menu_continue_chat")
async def continue_chat(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "ru"

        active = await chat_repo.get_active_session(user_id)
        ticket_code = active.ticket_code if active else None

        await chat_repo.activate_ai(user_id)

    await callback.message.delete()
    await callback.message.answer(
        get_text("chat_continued", language),
        reply_markup=get_chat_keyboard(language, ticket_code),
    )
    await state.set_state(UserStates.chatting)
    await callback.answer()


@router.callback_query(F.data == "menu_settings")
async def open_settings(callback: CallbackQuery):
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "ru"

    try:
        await callback.message.edit_caption(
            caption=get_text("settings", language),
            reply_markup=get_settings_keyboard(language),
        )
    except Exception:
        await callback.message.answer(
            get_text("settings", language),
            reply_markup=get_settings_keyboard(language),
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
        language = user.language if user else "ru"

        has_history = False
        active_session = await chat_repo.get_active_session(user_id)
        if active_session:
            history = await chat_repo.get_session_history(active_session.id, limit=1)
            has_history = len(history) > 0

    try:
        await callback.message.edit_caption(
            caption=get_text("greeting", language),
            reply_markup=get_main_menu_keyboard(language, has_history=has_history),
        )
    except Exception:
        await callback.message.answer(
            get_text("greeting", language),
            reply_markup=get_main_menu_keyboard(language, has_history=has_history),
        )
    await callback.answer()


@router.callback_query(F.data == "close_case")
async def close_case(callback: CallbackQuery, state: FSMContext):
    """Закрытие кейса пользователем — показывает CSAT."""
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "ru"

        active = await chat_repo.get_active_session(user_id)
        if not active:
            await callback.answer(get_text("no_active_session", language), show_alert=True)
            return

        session_id = active.id
        await chat_repo.update_case_status(
            session_id=session_id,
            new_status="CLOSED",
            actor_id=user_id,
            actor_role="user",
            note="Закрыто пользователем",
        )

        # Открепляем сообщение с тикетом
        if active.pinned_message_id:
            try:
                await callback.bot.unpin_chat_message(
                    chat_id=callback.message.chat.id,
                    message_id=active.pinned_message_id,
                )
            except Exception as e:
                logger.warning("Не удалось открепить сообщение: %s", e)

    await state.clear()

    # Показываем CSAT — оценку только когда пользователь сам закрывает
    await callback.message.answer(
        get_text("case_closed_csat", language),
        reply_markup=get_csat_keyboard(language, session_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("csat_"))
async def handle_csat(callback: CallbackQuery):
    """Обрабатывает оценку CSAT (1-5)."""
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    # Формат: csat_{session_id}_{rating}
    if len(parts) < 3:
        await callback.answer()
        return

    try:
        session_id = int(parts[1])
        rating = int(parts[2])
    except ValueError:
        await callback.answer()
        return

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "ru"

        await chat_repo.add_csat(
            session_id=session_id,
            user_id=user_id,
            rating=rating,
            ai_handled=True,
        )

    await callback.message.edit_text(
        get_text("csat_thanks", language).format(rating=rating),
        reply_markup=get_main_menu_keyboard(language, has_history=False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("csat_comment_"))
async def handle_csat_with_comment(callback: CallbackQuery, state: FSMContext):
    """Запускает ввод текстового комментария к CSAT."""
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer()
        return

    try:
        session_id = int(parts[2])
        rating = int(parts[3])
    except ValueError:
        await callback.answer()
        return

    await state.update_data(csat_session_id=session_id, csat_rating=rating)
    from states.user_states import UserStates
    await state.set_state(UserStates.entering_csat_comment)

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(callback.from_user.id)
        language = user.language if user else "ru"

    await callback.message.edit_text(get_text("csat_comment_prompt", language))
    await callback.answer()
