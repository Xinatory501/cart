import html
import logging
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from config import settings
from database.database import get_session
from database.models import User
from database.repository import ChatRepository, TrainingRepository, UserRepository
from locales.loader import get_text
from services.ai_service import AIService
from services.thread_service import ThreadService

logger = logging.getLogger(__name__)
router = Router()


def _message_text_for_forward(message: Message) -> str:
    if message.text and message.text.strip():
        return message.text.strip()
    if message.caption and message.caption.strip():
        return message.caption.strip()
    if message.photo:
        return "[Фото]"
    if message.video:
        return "[Видео]"
    if message.document:
        return "[Документ]"
    if message.voice:
        return "[Голосовое сообщение]"
    if message.audio:
        return "[Аудио]"
    if message.sticker:
        return "[Стикер]"
    return "[Сообщение без текста]"


async def _is_admin_user(user_id: int) -> bool:
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        return bool(user and user.role == "admin")


async def _resolve_user_by_thread(thread_service: ThreadService, thread_id: int) -> Optional[User]:
    user_id = await thread_service.get_user_id_by_thread(thread_id)
    if not user_id:
        return None

    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


def _in_support_group(message_or_callback) -> bool:
    if not settings.SUPPORT_GROUP_ID:
        return False

    if hasattr(message_or_callback, "chat") and message_or_callback.chat:
        return message_or_callback.chat.id == settings.SUPPORT_GROUP_ID

    if hasattr(message_or_callback, "message") and message_or_callback.message:
        return message_or_callback.message.chat.id == settings.SUPPORT_GROUP_ID

    return False


@router.message(Command("ai"))
async def activate_ai_in_thread(message: Message):
    if not _in_support_group(message):
        return

    thread_id = message.message_thread_id
    if not thread_id:
        await message.answer("Команда работает только внутри топика.")
        return

    thread_service = ThreadService(message.bot)
    if not await thread_service.is_thread_owned_by_current_bot(thread_id):
        return

    user = await _resolve_user_by_thread(thread_service, thread_id)
    if not user:
        await message.answer("Пользователь для этой темы не найден.")
        return

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        await chat_repo.activate_ai(user.id)

    await message.answer(f"AI включен для пользователя {user.id}.")

    try:
        await message.bot.send_message(
            chat_id=user.id,
            text=get_text("ai_activated", user.language),
        )
    except Exception as error:
        logger.error("Failed to notify user %s: %s", user.id, error)


@router.callback_query(F.data.startswith("ai_reply_"))
async def ai_reply_handler(callback: CallbackQuery):
    if not _in_support_group(callback):
        return

    if not callback.message:
        return

    thread_id = callback.message.message_thread_id
    if not thread_id:
        return

    thread_service = ThreadService(callback.bot)
    if not await thread_service.is_thread_owned_by_current_bot(thread_id):
        return

    user = await _resolve_user_by_thread(thread_service, thread_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        active_session = await chat_repo.get_active_session(user.id)

        if not active_session:
            await callback.answer("Нет активной сессии", show_alert=True)
            return

        history = await chat_repo.get_session_history(active_session.id, limit=30)
        messages = [
            {"role": "assistant" if item.role == "support" else item.role, "content": item.content}
            for item in history
            if item.role in {"user", "assistant", "support"}
        ]
        if len(messages) > 20:
            messages = messages[-20:]

    ai_service = await AIService.get_service()
    if not ai_service:
        await callback.answer("AI недоступен", show_alert=True)
        return

    await callback.answer("Генерирую AI-ответ...")

    async with get_session() as session:
        training_repo = TrainingRepository(session)
        system_prompt = await ai_service.get_system_prompt(training_repo, user.language)

    response = await ai_service.get_response(messages, system_prompt)
    safe_response = html.escape(response)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Вернуть в AI", callback_data=f"resend_to_ai_{user.id}")],
            [InlineKeyboardButton(text="Заблокировать", callback_data=f"ban_user_{user.id}")],
        ]
    )

    await callback.message.bot.send_message(
        chat_id=settings.SUPPORT_GROUP_ID,
        message_thread_id=thread_id,
        text=f"AI ответ:\n\n{response}",
        reply_markup=keyboard,
    )

    try:
        await callback.message.bot.send_message(
            chat_id=user.id,
            text=get_text("support_response", user.language).format(text=safe_response),
            parse_mode="HTML",
        )

        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.add_message(
                user.id,
                "support",
                response,
                is_ai_handled=False,
            )
            await chat_repo.deactivate_ai(user.id)

    except Exception as error:
        logger.error("Failed to deliver AI support response to user %s: %s", user.id, error)
        try:
            await thread_service.send_log_message(
                f"Failed to deliver AI support response. user_id={user.id} error={error}"
            )
        except Exception:
            pass
        await callback.message.answer("Не удалось отправить пользователю. Попробуйте позже.")


@router.callback_query(F.data.startswith("resend_to_ai_"))
async def resend_to_ai_handler(callback: CallbackQuery):
    if not _in_support_group(callback):
        return

    if not callback.message:
        return

    if not await _is_admin_user(callback.from_user.id):
        await callback.answer("Только администраторы", show_alert=True)
        return

    thread_id = callback.message.message_thread_id
    if not thread_id:
        return

    thread_service = ThreadService(callback.bot)
    if not await thread_service.is_thread_owned_by_current_bot(thread_id):
        return

    user = await _resolve_user_by_thread(thread_service, thread_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        await chat_repo.activate_ai(user.id)

    await callback.message.bot.send_message(
        chat_id=settings.SUPPORT_GROUP_ID,
        message_thread_id=thread_id,
        text=f"Пользователь {user.id} возвращен в AI.",
    )

    try:
        await callback.message.bot.send_message(
            chat_id=user.id,
            text=get_text("ai_activated", user.language),
        )
    except Exception as error:
        logger.error("Failed to notify user %s: %s", user.id, error)

    await callback.answer("Готово", show_alert=True)


@router.callback_query(F.data.startswith("ban_user_"))
async def ban_user_handler(callback: CallbackQuery):
    if not _in_support_group(callback):
        return

    if not callback.message:
        return

    if not await _is_admin_user(callback.from_user.id):
        await callback.answer("Только администраторы", show_alert=True)
        return

    thread_id = callback.message.message_thread_id
    if not thread_id:
        return

    thread_service = ThreadService(callback.bot)
    if not await thread_service.is_thread_owned_by_current_bot(thread_id):
        return

    user = await _resolve_user_by_thread(thread_service, thread_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    async with get_session() as session:
        user_repo = UserRepository(session)
        await user_repo.ban_user(user.id, None)

    await callback.message.bot.send_message(
        chat_id=settings.SUPPORT_GROUP_ID,
        message_thread_id=thread_id,
        text=f"Пользователь {user.id} заблокирован.",
    )

    try:
        await callback.message.bot.send_message(chat_id=user.id, text=get_text("banned", user.language))
    except Exception:
        pass

    await callback.answer("Пользователь заблокирован", show_alert=True)


@router.message(F.message_thread_id)
async def handle_support_message(message: Message):
    if not _in_support_group(message):
        return

    if message.from_user.is_bot:
        return

    if message.text and message.text.startswith("/"):
        return

    thread_id = message.message_thread_id
    thread_service = ThreadService(message.bot)

    if not await thread_service.is_thread_owned_by_current_bot(thread_id):
        return

    user = await _resolve_user_by_thread(thread_service, thread_id)
    if not user:
        return

    forwarded_text = _message_text_for_forward(message)
    safe_text = html.escape(forwarded_text)

    was_ai_active = False
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        active_session = await chat_repo.get_active_session(user.id)
        was_ai_active = bool(active_session and active_session.is_ai_active)
        await chat_repo.deactivate_ai(user.id)

    try:
        await message.bot.send_message(
            chat_id=user.id,
            text=get_text("support_response", user.language).format(text=safe_text),
            parse_mode="HTML",
        )

        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.add_message(
                user.id,
                "support",
                forwarded_text,
                is_ai_handled=False,
            )

        if was_ai_active:
            await message.answer("? Сообщение отправлено пользователю. AI выключен.")
        else:
            await message.answer("? Сообщение отправлено пользователю.")

    except Exception as error:
        logger.error("Failed to forward support message to user %s: %s", user.id, error)
        try:
            await thread_service.send_log_message(
                f"Failed to forward support message. user_id={user.id} error={error}"
            )
        except Exception:
            pass
        await message.answer("Не удалось отправить сообщение пользователю. Попробуйте позже.")


