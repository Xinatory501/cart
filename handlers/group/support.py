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
from database.repository import ChatRepository, TrainingRepository, UserRepository, ConfigRepository
from locales.loader import get_text
from services.ai_service import AIService
from services.thread_service import ThreadService
from services.translation_service import (
    TranslationDraft,
    store_draft,
    get_draft,
    remove_draft,
    update_draft_translation,
    translate_text,
    get_send_both_setting,
    set_send_both_setting,
    TEMPLATES,
)

logger = logging.getLogger(__name__)
router = Router()

LANG_INFO = {
    "ru": {"name": "Русский", "flag": "🇷🇺"},
    "en": {"name": "Английский", "flag": "🇬🇧"},
    "uz": {"name": "Узбекский", "flag": "🇺🇿"},
    "kz": {"name": "Казахский", "flag": "🇰🇿"},
}



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


def _format_info_text(
    user: User,
    ticket_number: Optional[str],
    links: list[tuple[str, str, int]],
) -> str:
    username = f"@{user.username}" if user.username else "Не указан"
    lines = [
        "<b>Информация по обращению</b>",
        "",
        f"Номер обращения: <code>{ticket_number or 'Не присвоен'}</code>",
        f"User ID: <code>{user.id}</code>",
        f"Username: {username}",
        f"Имя: {user.first_name or 'Не указано'}",
    ]

    if links:
        lines.extend(["", "<b>Обращения</b>"])
        for bot_key, link, thread_id in links:
            lines.append(f"• {bot_key}: <a href=\"{link}\">{thread_id}</a>")

    return "\n".join(lines)


@router.message(Command("ai"), _in_support_group)
async def activate_ai_in_thread(message: Message):

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


@router.message(F.text, _in_support_group, F.text.lower().startswith("инфо"))
async def show_ticket_info(message: Message):

    if message.from_user.is_bot:
        return

    text = (message.text or "").strip()
    if not text.lower().startswith("инфо"):
        return

    query = text[4:].strip()
    if not query:
        await message.answer("Использование: инфо @username, инфо 123456789 или инфо 00000001")
        return

    thread_service = ThreadService(message.bot)
    user = None

    async with get_session() as session:
        user_repo = UserRepository(session)

        if query.startswith("@"):
            user = await user_repo.get_by_username(query)
        else:
            ticket_user_id = await thread_service.get_user_id_by_ticket_number(query)
            if ticket_user_id:
                user = await user_repo.get_by_id(ticket_user_id)
            elif query.isdigit():
                user = await user_repo.get_by_id(int(query))
            else:
                user = await user_repo.get_by_username(query)

    if not user:
        await message.answer("Ничего не найдено.")
        return

    ticket_number = await thread_service.get_ticket_number(user.id)
    links = await thread_service.get_user_ticket_links(user.id)
    await message.answer(
        _format_info_text(user, ticket_number, links),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )




@router.message(F.message_thread_id, _in_support_group)
async def handle_support_message(message: Message):
    if message.from_user.is_bot:
        return

    if message.text and message.text.startswith("/"):
        return

    if message.text and message.text.strip().lower().startswith("инфо"):
        return

    thread_id = message.message_thread_id
    thread_service = ThreadService(message.bot)

    is_text = bool(message.text)
    is_photo = bool(message.photo)
    is_sticker = bool(message.sticker)
    is_gif = bool(message.animation)
    
    if not (is_text or is_photo or is_sticker or is_gif):
        logger.info("Ignoring support group message of unsupported type: %s", message.content_type)
        return

    user = await _resolve_user_by_thread(thread_service, thread_id)
    if not user:
        logger.warning("Could not resolve user for thread %s", thread_id)
        return

    logger.info("Resolved user %s for thread %s", user.id, thread_id)

    # Intercept text message if user's language is NOT Russian
    if is_text and user.language != "ru":
        # Deactivate AI immediately so AI doesn't reply in the meantime
        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.deactivate_ai(user.id)
            
        lang_info = LANG_INFO.get(user.language, {"name": user.language, "flag": ""})
        lang_name = lang_info["name"]
        lang_flag = lang_info["flag"]
        
        # Send a temporary loading message to keep the UI clean
        sent_msg = await message.answer(
            f"⏳ <i>Переводим ответ оператора на {lang_name.lower()} {lang_flag}...</i>",
            parse_mode="HTML"
        )
        
        # Do the translation
        translation = await translate_text(message.text, user.language)
        
        if translation:
            send_both = await get_send_both_setting()
            if send_both:
                final_text = f"{translation}\n\n---\n{message.text}"
            else:
                final_text = translation
                
            try:
                # Deliver to Web User (user.id < 0)
                if user.id < 0:
                    from services.api_service import send_to_web_user
                    
                    op_user = message.from_user
                    op_name = op_user.full_name or op_user.username or "Оператор"
                    if op_user.username:
                        op_name = f"{op_name} (@{op_user.username})"
                        
                    web_payload = get_text("support_response", user.language).format(text=html.escape(final_text))
                    
                    async with get_session() as session:
                        chat_repo = ChatRepository(session)
                        await send_to_web_user(user.id, web_payload, role="support")
                        await chat_repo.add_message(
                            user.id, "support", web_payload,
                            is_ai_handled=False, operator_name=op_name
                        )
                # Deliver to Telegram User
                else:
                    formatted_text = get_text("support_response", user.language).format(text=html.escape(final_text))
                    await message.bot.send_message(
                        chat_id=user.id,
                        text=formatted_text,
                        parse_mode="HTML"
                    )
                    
                    async with get_session() as session:
                        chat_repo = ChatRepository(session)
                        await chat_repo.add_message(
                            user.id, "support", final_text, is_ai_handled=False,
                        )
                
                # Update status message in group
                await sent_msg.edit_text(
                    f"✅ <b>Отправлено пользователю на {lang_name.lower()} {lang_flag}:</b>\n"
                    f"{html.escape(translation)}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error("Immediate translation send failed: %s", e)
                await sent_msg.edit_text(
                    f"❌ Ошибка при отправке перевода: {e}\n\n"
                    f"Оригинал: {html.escape(message.text)}",
                    parse_mode="HTML"
                )
        else:
            await sent_msg.edit_text(
                f"❌ Не удалось выполнить перевод на {lang_name.lower()} {lang_flag}.\n"
                f"Сообщение не отправлено. Пожалуйста, попробуйте еще раз.",
                parse_mode="HTML"
            )
        return



    # Normal delivery flow (for Russian users or non-text media)
    was_ai_active = False
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        active_session = await chat_repo.get_active_session(user.id)
        was_ai_active = bool(active_session and active_session.is_ai_active)
        await chat_repo.deactivate_ai(user.id)

    web_payload = ""
    forwarded_text = ""
    file_id = None
    file_ext = ".jpg"

    if message.text:
        forwarded_text = message.text.strip()
        safe_text = html.escape(forwarded_text)
        web_payload = get_text("support_response", user.language).format(text=safe_text)
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_ext = ".jpg"
        forwarded_text = "[Фото]"
    elif message.sticker:
        file_id = message.sticker.file_id
        file_ext = ".webp"
        forwarded_text = "[Стикер]"
    elif message.animation:
        file_id = message.animation.file_id
        file_ext = ".mp4"
        forwarded_text = "[Анимация]"

    if file_id:
        try:
            bot = message.bot
            file_info = await bot.get_file(file_id)
            file_path = file_info.file_path
            
            import os
            import secrets
            unique_filename = f"tg_{secrets.token_hex(8)}{file_ext}"
            local_path = os.path.join('/app/data/uploads', unique_filename)
            os.makedirs('/app/data/uploads', exist_ok=True)
            
            await bot.download_file(file_path, local_path)
            file_url = f"/uploads/{unique_filename}"
            
            async with get_session() as session:
                config_repo = ConfigRepository(session)
                await config_repo.set(f"media_file_id:{unique_filename}", file_id)
            
            if file_ext == ".mp4":
                web_payload = f'<video autoplay loop muted playsinline src="{file_url}" style="max-width: 250px; border-radius: 8px;" onclick="window.open(this.src)"></video>'
            elif file_ext == ".webp":
                web_payload = f'<img src="{file_url}" style="max-width: 120px;" />'
            else:
                web_payload = f'<span class="photo-link-text" style="color: #3880ff; font-weight: 600; cursor: pointer; text-decoration: underline; display: inline-flex; align-items: center; gap: 4px;" data-src="{file_url}">📷 Фото</span>'
                
            if message.caption and message.caption.strip():
                web_payload += f'<div style="margin-top: 6px;">{html.escape(message.caption.strip())}</div>'
                forwarded_text += f": {message.caption.strip()}"
        except Exception as e:
            logger.error("Failed to download media: %s", e)
            await message.answer(f"❌ Ошибка загрузки медиафайла: {e}")
            return

    if user.id < 0:
        try:
            from services.api_service import send_to_web_user
            
            op_user = message.from_user
            op_name = op_user.full_name or op_user.username or "Оператор"
            if op_user.username:
                op_name = f"{op_name} (@{op_user.username})"
                
            async with get_session() as session:
                chat_repo = ChatRepository(session)
                
                if was_ai_active:
                    transferred_messages = {
                        "ru": "💬 Вы переведены в режим общения с оператором поддержки.",
                        "en": "💬 You have been transferred to the support operator chat.",
                        "uz": "💬 Siz qo'llab-quvvatlash operatori bilan muloqot rejimiga o'tkazildingiz.",
                        "kz": "💬 Сіз қолдау көрсету операторымен сөйлесу режиміне ауыстырылдыңыз.",
                    }
                    notify_text = transferred_messages.get(user.language, transferred_messages["ru"])
                    await send_to_web_user(
                        user.id,
                        notify_text,
                        role="support"
                    )
                    await chat_repo.add_message(
                        user.id,
                        "support",
                        notify_text,
                        is_ai_handled=False,
                    )
                
                await send_to_web_user(
                    user.id,
                    web_payload,
                    role="support"
                )
                
                await chat_repo.add_message(
                    user.id,
                    "support",
                    web_payload,
                    is_ai_handled=False,
                    operator_name=op_name
                )

            if was_ai_active:
                await message.answer("💬 Сообщение отправлено на сайт. AI выключен.")
            else:
                await message.answer("💬 Сообщение отправлено на сайт.")
        except Exception as error:
            logger.error("Failed to forward support message to web user %s: %s", user.id, error)
            await message.answer(f"❌ Ошибка отправки на сайт: {error}")
        return

    try:
        await message.copy_to(chat_id=user.id)

        async with get_session() as session:
            chat_repo = ChatRepository(session)
            await chat_repo.add_message(
                user.id,
                "support",
                forwarded_text,
                is_ai_handled=False,
            )

        if was_ai_active:
            await message.answer("💬 Сообщение отправлено пользователю. AI выключен.")
        else:
            await message.answer("💬 Сообщение отправлено пользователю.")

    except Exception as error:
        logger.error("Failed to forward support message to user %s: %s", user.id, error)
        try:
            await thread_service.send_log_message(
                f"Failed to forward support message. user_id={user.id} error={error}"
            )
        except Exception:
            pass
        await message.answer("Не удалось отправить сообщение пользователю. Попробуйте позже.")


