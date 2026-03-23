import html
import logging
import re
from typing import Dict, List

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import settings
from database.database import get_session
from database.repository import (
    ChatRepository,
    PendingRequestRepository,
    TrainingRepository,
    UserRepository,
)
from keyboards.menu import get_main_menu_keyboard, get_try_ai_again_keyboard
from locales.loader import get_text
from services.ai_service import AIService
from services.bot_profile_service import set_user_bot_key
from services.thread_service import ThreadService
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


async def _mark_pending(request_id: int, failed: bool = False) -> None:
    if not request_id:
        return

    async with get_session() as session:
        pending_repo = PendingRequestRepository(session)
        if failed:
            await pending_repo.mark_failed(request_id)
        else:
            await pending_repo.mark_completed(request_id)


@router.message(UserStates.chatting, F.text)
async def handle_chat_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_message = (message.text or "").strip()

    if not user_message:
        return

    if user_message.startswith("/admin") or user_message.startswith("/start"):
        return

    language = "en"
    username = None
    first_name = None
    thread_id = None
    pending_request_id = None
    active_session_id = None

    thread_service = ThreadService(message.bot)

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        pending_repo = PendingRequestRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user:
            return

        language = user.language
        username = user.username
        first_name = user.first_name
        thread_id = user.thread_id
        await set_user_bot_key(user_id, thread_service.profile.key)

        active_session = await chat_repo.get_active_session(user_id)
        if not active_session:
            await message.answer(get_text("no_active_session", language))
            return

        active_session_id = active_session.id

        if is_direct_human_request(user_message):
            await chat_repo.deactivate_ai(user_id)
            await chat_repo.add_message(
                user_id=user_id,
                role="user",
                content=user_message,
                message_id=message.message_id,
                is_ai_handled=False,
            )

            await state.set_state(UserStates.chatting)
            await message.answer(get_text("human_called", language), parse_mode="HTML")

            if settings.SUPPORT_GROUP_ID:
                await thread_service.notify_human_needed(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                )
                await thread_service.send_user_message(
                    user_id=user_id,
                    text=user_message,
                    username=username,
                    first_name=first_name,
                )
            return

        if not active_session.is_ai_active:
            await chat_repo.add_message(
                user_id=user_id,
                role="user",
                content=user_message,
                message_id=message.message_id,
                is_ai_handled=False,
            )

            if settings.SUPPORT_GROUP_ID:
                await thread_service.send_user_message(
                    user_id=user_id,
                    text=user_message,
                    username=username,
                    first_name=first_name,
                )
            return

        await chat_repo.add_message(
            user_id=user_id,
            role="user",
            content=user_message,
            message_id=message.message_id,
            is_ai_handled=True,
        )

        pending = await pending_repo.create(
            user_id=user_id,
            message_text=user_message,
            message_id=message.message_id,
            session_id=active_session_id,
        )
        pending_request_id = pending.id

        history = await chat_repo.get_session_history(active_session_id, limit=40)
        messages = [
            {"role": item.role, "content": item.content}
            for item in history
            if item.role in {"user", "assistant"}
        ]
        messages = _trim_history(messages)

    ai_service = await AIService.get_service()
    if not ai_service:
        await thread_service.send_log_message(
            f"AI service unavailable. user_id={user_id}"
        )
        await _mark_pending(pending_request_id, failed=True)
        await message.answer(
            get_text("error_try_later", language),
            reply_markup=get_try_ai_again_keyboard(language),
        )
        return

    async with get_session() as session:
        training_repo = TrainingRepository(session)
        system_prompt = await ai_service.get_system_prompt(training_repo, language)

    response_parts: List[str] = []
    stream_error: Exception | None = None
    try:
        async for chunk in ai_service.get_response_stream(
            messages=messages,
            system_prompt=system_prompt,
            user_id=user_id,
            thread_id=thread_id,
            bot=message.bot,
        ):
            response_parts.append(chunk)
    except Exception as error:
        stream_error = error
        logger.error("AI stream crashed for user %s: %s", user_id, error)

    response_text = "".join(response_parts).strip()
    if not response_text:
        await thread_service.send_log_message(
            f"Empty AI response. user_id={user_id} error={stream_error}"
        )
        await _mark_pending(pending_request_id, failed=True)
        await message.answer(get_text("error_try_later", language))
        return

    lowered = response_text.lower()
    if "ignore_offtopic" in lowered:
        off_topic_text = get_text("off_topic", language)
        if settings.SUPPORT_GROUP_ID:
            await thread_service.send_system_message(
                user_id=user_id,
                text="AI пометил вопрос как оффтоп. Сообщение пользователя передано в поддержку.",
                username=username,
                first_name=first_name,
            )
            await thread_service.send_user_message(
                user_id=user_id,
                text=user_message,
                username=username,
                first_name=first_name,
            )
            await thread_service.send_ai_message(
                user_id=user_id,
                text=off_topic_text,
                username=username,
                first_name=first_name,
            )
        await _mark_pending(pending_request_id, failed=False)
        await message.answer(off_topic_text)
        return

    clean_text = (
        response_text
        .replace("ignore_offtopic", "")
        .replace("IGNORE_OFFTOPIC", "")
        .replace("call_people", "")
        .replace("CALL_PEOPLE", "")
        .strip()
    )

    if not clean_text:
        await thread_service.send_log_message(
            f"AI response empty after cleaning. user_id={user_id}"
        )
        await _mark_pending(pending_request_id, failed=True)
        await message.answer(get_text("error_try_later", language))
        return

    async with get_session() as session:
        chat_repo = ChatRepository(session)

        if "call_people" in lowered:
            await chat_repo.deactivate_ai(user_id)

            html_response = markdown_to_html(clean_text)
            await message.answer(html_response, parse_mode="HTML")
            await message.answer(get_text("human_called", language), parse_mode="HTML")

            await chat_repo.add_message(
                user_id=user_id,
                role="assistant",
                content=clean_text,
            )

            if settings.SUPPORT_GROUP_ID:
                await thread_service.notify_human_needed(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                )
                await thread_service.send_user_message(
                    user_id=user_id,
                    text=user_message,
                    username=username,
                    first_name=first_name,
                )
                await thread_service.send_ai_message(
                    user_id=user_id,
                    text=clean_text,
                    username=username,
                    first_name=first_name,
                )

            await _mark_pending(pending_request_id, failed=False)
            return

        html_response = markdown_to_html(clean_text)
        response_msg = await message.answer(html_response, parse_mode="HTML")

        await chat_repo.add_message(
            user_id=user_id,
            role="assistant",
            content=clean_text,
            message_id=response_msg.message_id,
        )

    if settings.SUPPORT_GROUP_ID:
        await thread_service.send_user_message(
            user_id=user_id,
            text=user_message,
            username=username,
            first_name=first_name,
        )
        await thread_service.send_ai_message(
            user_id=user_id,
            text=clean_text,
            username=username,
            first_name=first_name,
        )

    await _mark_pending(pending_request_id, failed=False)


@router.message(UserStates.chatting)
async def handle_non_text_message(message: Message):
    user_id = message.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "en"
        await message.answer(get_text("text_only", language))


@router.callback_query(F.data == "try_ai_again")
async def try_ai_again(callback: CallbackQuery):
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "en"

    ai_service = await AIService.get_service()

    if ai_service:
        await callback.answer("AI is available. You can continue.", show_alert=True)
        await callback.message.edit_text(
            "AI is available again. Send your question.",
            reply_markup=None,
        )
    else:
        await callback.answer("AI is still unavailable. Try later.", show_alert=True)


@router.message(~StateFilter(UserStates.chatting), F.text)
async def handle_text_outside_chat(message: Message, state: FSMContext):
    if settings.SUPPORT_GROUP_ID and message.chat.id == settings.SUPPORT_GROUP_ID:
        return

    current_state = await state.get_state()
    if current_state and current_state.startswith("AdminStates:"):
        return

    user_id = message.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user:
            return

        language = user.language

        has_history = False
        active_session = await chat_repo.get_active_session(user_id)
        if active_session:
            history = await chat_repo.get_session_history(active_session.id, limit=1)
            has_history = len(history) > 0

        await message.answer(
            get_text("not_in_chat_state", language),
            reply_markup=get_main_menu_keyboard(language, has_history),
        )
