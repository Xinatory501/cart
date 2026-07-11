import html
import logging
import re
from typing import Dict, List, Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import settings
from database.database import get_session
from database.repository import (
    ChatRepository,
    ClarificationRepository,
    PendingRequestRepository,
    TrainingRepository,
    UserRepository,
)
from keyboards.menu import get_main_menu_keyboard, get_try_ai_again_keyboard
from locales.loader import get_text
from services.ai_service import AIService
from services.bot_profile_service import set_user_bot_key
from services.thread_service import ThreadService
from services.working_hours_service import get_next_shift_info, is_operator_available
from states.user_states import UserStates

logger = logging.getLogger(__name__)
router = Router()

HUMAN_REQUEST_KEYWORDS = [
    "call people",
    "call person",
    "call operator",
    "call human",
    "call support",
    "call_people",
    "connect me",
    "talk to human",
    "оператор",
    "человек",
    "поддержка",
]


def is_direct_human_request(text: str) -> bool:
    text_lower = text.lower().strip()
    return any(keyword in text_lower for keyword in HUMAN_REQUEST_KEYWORDS)


def markdown_to_html(text: str) -> str:
    text = html.escape(text or "")
    text = re.sub(r"\*\*([^\*]+?)\*\*", r"<b>\1</b>", text, flags=re.UNICODE)
    text = re.sub(r"\*([^\*]+?)\*", r"<i>\1</i>", text, flags=re.UNICODE)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text, flags=re.UNICODE)
    text = re.sub(r"\[([^\]]+?)\]\(([^\)]+?)\)", r"<a href=\"\2\">\1</a>", text, flags=re.UNICODE)
    return text


def _trim_history(messages: List[Dict[str, str]], keep_recent: int = 20) -> List[Dict[str, str]]:
    if len(messages) <= keep_recent:
        return messages

    old_part = messages[:-keep_recent]
    recent_part = messages[-keep_recent:]

    user_questions = [item["content"] for item in old_part if item["role"] == "user"]
    summary = "Earlier context summary: "
    if user_questions:
        summary += "; ".join(q[:80] for q in user_questions[:5])
    else:
        summary += "general user support conversation"

    return [{"role": "system", "content": summary}] + recent_part


def _short_text(text: str, limit: int = 120) -> str:
    value = (text or "").replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


async def _mark_pending(request_id: Optional[int], failed: bool = False) -> None:
    if not request_id:
        return

    logger.info("pending.mark request_id=%s failed=%s", request_id, failed)
    async with get_session() as session:
        pending_repo = PendingRequestRepository(session)
        if failed:
            await pending_repo.mark_failed(request_id)
        else:
            await pending_repo.mark_completed(request_id)


async def _get_user_language_and_history_flag(user_id: int) -> tuple[str, bool]:
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "en"

        has_history = False
        active_session = await chat_repo.get_active_session(user_id)
        if active_session:
            history = await chat_repo.get_session_history(active_session.id, limit=1)
            has_history = len(history) > 0

        return language, has_history


async def _load_active_chat_context(user_id: int, bot) -> Optional[dict]:
    thread_service = ThreadService(bot)

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        clarification_repo = ClarificationRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user:
            logger.warning("chat.context.user_missing user_id=%s", user_id)
            return None

        await set_user_bot_key(user_id, thread_service.profile.key)

        clarification = await clarification_repo.get_active(user_id)
        active_session = await chat_repo.get_active_session(user_id)

        return {
            "user": user,
            "thread_service": thread_service,
            "clarification": clarification,
            "active_session": active_session,
        }


async def _handle_human_request(
    message: Message,
    state: FSMContext,
    user,
    thread_service: ThreadService,
    active_session_id: int,
    user_message: str,
) -> None:
    # ── Working hours check ──────────────────────────────────────────
    if not await is_operator_available():
        next_shift = await get_next_shift_info(user.language)
        offline_text = get_text("operator_offline", user.language, next_shift=next_shift)
        reactivate_btn = get_text("reactivate_ai", user.language)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=reactivate_btn, callback_data="reactivate_ai")]
            ]
        )
        # Still deactivate AI and register the request so operator sees it
        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.deactivate_ai(user.id)
            await chat_repo.add_message(
                user_id=user.id,
                role="user",
                content=user_message,
                message_id=message.message_id,
                is_ai_handled=False,
            )
        await state.set_state(UserStates.chatting)
        await message.answer(offline_text, parse_mode="HTML", reply_markup=kb)
        # Still notify support group so operators see it when they come online
        if settings.SUPPORT_GROUP_ID:
            await thread_service.notify_human_needed(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
            await thread_service.send_user_message(
                user_id=user.id,
                text=user_message,
                username=user.username,
                first_name=user.first_name,
                user_language=user.language,
            )
        logger.info(
            "chat.human_request.offline user_id=%s session_id=%s",
            user.id,
            active_session_id,
        )
        return
    # ────────────────────────────────────────────────────────────────

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        await chat_repo.deactivate_ai(user.id)
        await chat_repo.add_message(
            user_id=user.id,
            role="user",
            content=user_message,
            message_id=message.message_id,
            is_ai_handled=False,
        )

    await state.set_state(UserStates.chatting)
    await message.answer(get_text("human_called", user.language), parse_mode="HTML")

    if settings.SUPPORT_GROUP_ID:
        await thread_service.notify_human_needed(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )
        await thread_service.send_user_message(
            user_id=user.id,
            text=user_message,
            username=user.username,
            first_name=user.first_name,
            user_language=user.language,
        )

    logger.info(
        "chat.human_request user_id=%s session_id=%s text=%r",
        user.id,
        active_session_id,
        _short_text(user_message),
    )


async def _build_messages_for_session(session_id: int) -> List[Dict[str, str]]:
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        history = await chat_repo.get_session_history(session_id, limit=40)

    messages = [
        {"role": item.role, "content": item.content}
        for item in history
        if item.role in {"user", "assistant"}
    ]
    return _trim_history(messages)


async def _get_system_prompt(ai_service: AIService, language: str) -> str:
    async with get_session() as session:
        training_repo = TrainingRepository(session)
        return await ai_service.get_system_prompt(training_repo, language)


async def _process_ai_response(
    message: Message,
    state: FSMContext,
    user,
    thread_service: ThreadService,
    source_text: str,
    active_session_id: int,
    messages: List[Dict[str, str]],
    pending_request_id: Optional[int] = None,
) -> None:
    ai_service = await AIService.get_service()
    if not ai_service:
        logger.error("chat.ai_service_missing user_id=%s pending_id=%s", user.id, pending_request_id)
        await thread_service.send_log_message(f"AI service unavailable. user_id={user.id}")
        await _mark_pending(pending_request_id, failed=True)
        await message.answer(
            get_text("error_try_later", user.language),
            reply_markup=get_try_ai_again_keyboard(user.language),
        )
        return

    system_prompt = await _get_system_prompt(ai_service, user.language)
    logger.info(
        "chat.ai_start user_id=%s session_id=%s pending_id=%s provider=%s model=%s history_items=%s",
        user.id,
        active_session_id,
        pending_request_id,
        ai_service.provider.name,
        ai_service.model.model_name,
        len(messages),
    )

    response_parts: List[str] = []
    stream_error: Exception | None = None
    try:
        async for chunk in ai_service.get_response_stream(
            messages=messages,
            system_prompt=system_prompt,
            user_id=user.id,
            thread_id=user.thread_id,
            bot=message.bot,
        ):
            response_parts.append(chunk)
    except Exception as error:
        stream_error = error
        logger.exception("chat.ai_stream_error user_id=%s pending_id=%s", user.id, pending_request_id)

    response_text = "".join(response_parts).strip()
    logger.info(
        "chat.ai_done user_id=%s pending_id=%s chunks=%s response_len=%s",
        user.id,
        pending_request_id,
        len(response_parts),
        len(response_text),
    )

    if not response_text:
        await thread_service.send_log_message(
            f"Empty AI response. user_id={user.id} pending_id={pending_request_id} error={stream_error}"
        )
        await _mark_pending(pending_request_id, failed=True)
        await message.answer(get_text("error_try_later", user.language))
        return

    lowered = response_text.lower()
    if "ignore_offtopic" in lowered:
        off_topic_text = get_text("off_topic", user.language)
        if settings.SUPPORT_GROUP_ID:
            await thread_service.send_system_message(
                user_id=user.id,
                text="AI пометил вопрос как оффтоп. Сообщение пользователя передано в поддержку.",
                username=user.username,
                first_name=user.first_name,
            )
            await thread_service.send_user_message(
                user_id=user.id,
                text=source_text,
                username=user.username,
                first_name=user.first_name,
                user_language=user.language,
            )
            await thread_service.send_ai_message(
                user_id=user.id,
                text=off_topic_text,
                username=user.username,
                first_name=user.first_name,
            )
        await _mark_pending(pending_request_id, failed=False)
        await message.answer(off_topic_text)
        return

    if "need_clarification" in lowered:
        clarification_text = (
            response_text
            .replace("need_clarification", "")
            .replace("NEED_CLARIFICATION", "")
            .strip()
        )
        if clarification_text:
            async with get_session() as session:
                clarification_repo = ClarificationRepository(session)
                await clarification_repo.create(
                    user_id=user.id,
                    session_id=active_session_id,
                    original_question=source_text,
                    clarification_question=clarification_text,
                )
            await state.set_state(UserStates.waiting_clarification)
            await _mark_pending(pending_request_id, failed=False)
            await message.answer(markdown_to_html(clarification_text), parse_mode="HTML")
            logger.info("chat.clarification_requested user_id=%s pending_id=%s", user.id, pending_request_id)
            return

    clean_text = (
        response_text
        .replace("ignore_offtopic", "")
        .replace("IGNORE_OFFTOPIC", "")
        .replace("call_people", "")
        .replace("CALL_PEOPLE", "")
        .replace("need_clarification", "")
        .replace("NEED_CLARIFICATION", "")
        .strip()
    )

    if not clean_text:
        logger.error("chat.clean_text_empty user_id=%s pending_id=%s", user.id, pending_request_id)
        await thread_service.send_log_message(
            f"AI response empty after cleaning. user_id={user.id} pending_id={pending_request_id}"
        )
        await _mark_pending(pending_request_id, failed=True)
        await message.answer(get_text("error_try_later", user.language))
        return

    if "call_people" in lowered:
        # ── Working hours check ──────────────────────────────────────
        if not await is_operator_available():
            next_shift = await get_next_shift_info(user.language)
            offline_text = get_text("operator_offline", user.language, next_shift=next_shift)
            reactivate_btn = get_text("reactivate_ai", user.language)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=reactivate_btn, callback_data="reactivate_ai")]
                ]
            )
            # Deactivate AI, register in support group, show offline notice
            async with get_session() as session:
                chat_repo = ChatRepository(session)
                await chat_repo.deactivate_ai(user.id)
                await chat_repo.add_message(user.id, "assistant", clean_text)

            await message.answer(markdown_to_html(clean_text), parse_mode="HTML")
            await message.answer(offline_text, parse_mode="HTML", reply_markup=kb)

            if settings.SUPPORT_GROUP_ID:
                await thread_service.notify_human_needed(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                )
                await thread_service.send_user_message(
                    user_id=user.id,
                    text=source_text,
                    username=user.username,
                    first_name=user.first_name,
                    user_language=user.language,
                )
                await thread_service.send_ai_message(
                    user_id=user.id,
                    text=clean_text,
                    username=user.username,
                    first_name=user.first_name,
                )

            await _mark_pending(pending_request_id, failed=False)
            await state.set_state(UserStates.chatting)
            logger.info("chat.call_people.offline user_id=%s pending_id=%s", user.id, pending_request_id)
            return
        # ────────────────────────────────────────────────────────────

        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.deactivate_ai(user.id)
            await chat_repo.add_message(user.id, "assistant", clean_text)

        await message.answer(markdown_to_html(clean_text), parse_mode="HTML")
        await message.answer(get_text("human_called", user.language), parse_mode="HTML")

        if settings.SUPPORT_GROUP_ID:
            await thread_service.notify_human_needed(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
            await thread_service.send_user_message(
                user_id=user.id,
                text=source_text,
                username=user.username,
                first_name=user.first_name,
                user_language=user.language,
            )
            await thread_service.send_ai_message(
                user_id=user.id,
                text=clean_text,
                username=user.username,
                first_name=user.first_name,
            )

        await _mark_pending(pending_request_id, failed=False)
        await state.set_state(UserStates.chatting)
        logger.info("chat.call_people user_id=%s pending_id=%s", user.id, pending_request_id)
        return

    response_message = await message.answer(markdown_to_html(clean_text), parse_mode="HTML")
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        await chat_repo.add_message(
            user_id=user.id,
            role="assistant",
            content=clean_text,
            message_id=response_message.message_id,
        )

    if settings.SUPPORT_GROUP_ID:
        await thread_service.send_user_message(
            user_id=user.id,
            text=source_text,
            username=user.username,
            first_name=user.first_name,
            user_language=user.language,
        )
        await thread_service.send_ai_message(
            user_id=user.id,
            text=clean_text,
            username=user.username,
            first_name=user.first_name,
        )

    await _mark_pending(pending_request_id, failed=False)
    await state.set_state(UserStates.chatting)
    logger.info(
        "chat.reply_sent user_id=%s pending_id=%s response_message_id=%s",
        user.id,
        pending_request_id,
        response_message.message_id,
    )


async def _handle_regular_chat(message: Message, state: FSMContext, user, active_session) -> None:
    user_message = (message.text or "").strip()
    thread_service = ThreadService(message.bot)

    logger.info(
        "chat.regular.start user_id=%s session_id=%s is_ai_active=%s text=%r",
        user.id,
        active_session.id,
        active_session.is_ai_active,
        _short_text(user_message),
    )

    if is_direct_human_request(user_message):
        await _handle_human_request(
            message=message,
            state=state,
            user=user,
            thread_service=thread_service,
            active_session_id=active_session.id,
            user_message=user_message,
        )
        return

    if not active_session.is_ai_active:
        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.add_message(
                user_id=user.id,
                role="user",
                content=user_message,
                message_id=message.message_id,
                is_ai_handled=False,
            )

        if settings.SUPPORT_GROUP_ID:
            await thread_service.send_user_message(
                user_id=user.id,
                text=user_message,
                username=user.username,
                first_name=user.first_name,
                user_language=user.language,
            )
        logger.info("chat.regular.ai_inactive user_id=%s session_id=%s", user.id, active_session.id)
        return

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        pending_repo = PendingRequestRepository(session)

        await chat_repo.add_message(
            user_id=user.id,
            role="user",
            content=user_message,
            message_id=message.message_id,
            is_ai_handled=True,
        )
        pending = await pending_repo.create(
            user_id=user.id,
            message_text=user_message,
            message_id=message.message_id,
            session_id=active_session.id,
        )

    messages = await _build_messages_for_session(active_session.id)
    await _process_ai_response(
        message=message,
        state=state,
        user=user,
        thread_service=thread_service,
        source_text=user_message,
        active_session_id=active_session.id,
        messages=messages,
        pending_request_id=pending.id,
    )


async def _handle_clarification_chat(message: Message, state: FSMContext, user, clarification) -> None:
    user_answer = (message.text or "").strip()
    thread_service = ThreadService(message.bot)

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        clarification_repo = ClarificationRepository(session)

        active_session = await chat_repo.get_active_session(user.id)
        if not active_session:
            await state.set_state(UserStates.chatting)
            await message.answer(get_text("no_active_session", user.language))
            logger.warning("chat.clarification.no_active_session user_id=%s", user.id)
            return

        original_question = clarification.original_question
        combined_question = f"{original_question}\n\nУточнение: {user_answer}"
        await clarification_repo.mark_answered(clarification.id)
        await chat_repo.add_message(
            user_id=user.id,
            role="user",
            content=combined_question,
            message_id=message.message_id,
            is_ai_handled=True,
        )

    messages = await _build_messages_for_session(active_session.id)
    logger.info(
        "chat.clarification.answer user_id=%s clarification_id=%s session_id=%s text=%r",
        user.id,
        clarification.id,
        active_session.id,
        _short_text(user_answer),
    )
    await _process_ai_response(
        message=message,
        state=state,
        user=user,
        thread_service=thread_service,
        source_text=combined_question,
        active_session_id=active_session.id,
        messages=messages,
        pending_request_id=None,
    )


@router.message(F.text)
async def handle_private_text(message: Message, state: FSMContext):
    if not message.from_user or not message.chat or message.chat.type != "private":
        return

    text = (message.text or "").strip()
    if not text:
        return

    get_ticket_texts = ["Узнать номер диалога", "Get ticket number", "Muloqot raqamini bilish", "Диалог нөмірін білу"]
    if text in get_ticket_texts:
        async with get_session() as session:
            chat_repo = ChatRepository(session)
            active_session = await chat_repo.get_active_session(message.from_user.id)
            if active_session and active_session.ticket_number:
                user_repo = UserRepository(session)
                user = await user_repo.get_by_id(message.from_user.id)
                language = user.language if user else "ru"
                await message.answer(
                    get_text("your_ticket_number", language).format(ticket_number=active_session.ticket_number),
                    parse_mode="HTML"
                )
            else:
                await message.answer("❌ Нет активного диалога.")
        return

    if text.startswith("/"):
        return

    logger.info(
        "chat.route.enter user_id=%s message_id=%s text=%r",
        message.from_user.id,
        message.message_id,
        _short_text(text),
    )

    context = await _load_active_chat_context(message.from_user.id, message.bot)
    if not context:
        return

    user = context["user"]
    clarification = context["clarification"]
    active_session = context["active_session"]

    if clarification:
        await state.set_state(UserStates.waiting_clarification)
        await _handle_clarification_chat(message, state, user, clarification)
        return

    if not active_session:
        language, has_history = await _get_user_language_and_history_flag(user.id)
        await message.answer(
            get_text("not_in_chat_state", language),
            reply_markup=get_main_menu_keyboard(language, has_history),
        )
        logger.info("chat.route.no_active_session user_id=%s", user.id)
        return

    await state.set_state(UserStates.chatting)
    await _handle_regular_chat(message, state, user, active_session)


@router.message(~F.text)
async def handle_private_non_text(message: Message):
    if not message.from_user or not message.chat or message.chat.type != "private":
        return

    context = await _load_active_chat_context(message.from_user.id, message.bot)
    if not context or not context["active_session"]:
        return

    await message.answer(get_text("text_only", context["user"].language))
    logger.info("chat.route.non_text user_id=%s message_id=%s", message.from_user.id, message.message_id)


@router.callback_query(F.data == "try_ai_again")
async def try_ai_again(callback: CallbackQuery):
    ai_service = await AIService.get_service()
    if ai_service:
        await callback.answer("AI is available. You can continue.", show_alert=True)
        await callback.message.edit_text(
            "AI is available again. Send your question.",
            reply_markup=None,
        )
        return

    await callback.answer("AI is still unavailable. Try later.", show_alert=True)


@router.callback_query(F.data == "reactivate_ai")
async def reactivate_ai_callback(callback: CallbackQuery, state: FSMContext):
    """User pressed 'Return to AI' after offline operator message."""
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            await callback.answer("Сессия не найдена.", show_alert=True)
            return
        await chat_repo.activate_ai(user_id)

    language = user.language
    ai_activated_text = get_text("ai_activated", language)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(ai_activated_text, parse_mode="HTML")
    await state.set_state(UserStates.chatting)
    await callback.answer()
    logger.info("chat.reactivate_ai user_id=%s", user_id)
