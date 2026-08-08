"""
Обработчик /start и выбора языка.
REG-06/REG-07: показывает языки экземпляра при первом запуске, не сбрасывает при повторном.
TG-13: показывает privacy consent перед первым использованием.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, FSInputFile, InlineKeyboardButton,
    InlineKeyboardMarkup, Message
)

from config import settings
from database.database import get_session
from database.repository import UserRepository, ConfigRepository
from keyboards.menu import get_main_menu_keyboard
from locales.loader import get_text
from services.bot_profile_service import get_default_language_for_bot, set_user_bot_key
from services.thread_service import ThreadService
from states.user_states import UserStates

logger = logging.getLogger(__name__)
router = Router()
BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "cartame.jpg"

PRIVACY_CONSENT_VERSION = "1.0"


def _get_language_keyboard(available_languages: List[str], current_language: Optional[str] = None) -> InlineKeyboardMarkup:
    """Строит клавиатуру выбора языка из доступных в экземпляре."""
    lang_labels = {
        "ru": "🇷🇺 Русский",
        "en": "🇬🇧 English",
        "kk": "🇰🇿 Қазақша",
        "kz": "🇰🇿 Қазақша",  # alias
        "uz": "🇺🇿 O'zbek",
        "be": "🇧🇾 Беларуская",
    }
    buttons = []
    for lang in available_languages:
        label = lang_labels.get(lang, lang.upper())
        if lang == current_language:
            label = "✅ " + label
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"lang_{lang}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _get_privacy_keyboard(language: str, privacy_url: Optional[str] = None) -> InlineKeyboardMarkup:
    """Клавиатура принятия/отклонения privacy consent."""
    buttons = [
        [InlineKeyboardButton(text=get_text("accept_privacy", language), callback_data="privacy_accept")],
        [InlineKeyboardButton(text=get_text("decline_privacy", language), callback_data="privacy_decline")],
    ]
    if privacy_url:
        buttons.insert(0, [InlineKeyboardButton(text="📄 Политика конфиденциальности", url=privacy_url)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    default_language = get_default_language_for_bot(message.bot)
    available_languages = settings.instance_languages or [default_language]

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)

        if not user:
            # Первый запуск — создаём пользователя, НЕ устанавливаем язык сразу
            user = await user_repo.create(user_id, username, first_name, last_name)
            is_new_user = True
            language = default_language
        else:
            # REG-07: не сбрасываем язык при повторном /start
            is_new_user = False
            language = user.language or default_language

    # Создаём тему в группе поддержки
    thread_service = ThreadService(message.bot)
    await thread_service.ensure_thread_for_user(
        user_id=user_id,
        username=username,
        first_name=first_name,
    )
    await set_user_bot_key(user_id, thread_service.profile.key)

    if is_new_user and len(available_languages) > 1:
        # REG-06: при первом запуске показываем выбор языка
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            privacy_url = await config_repo.get("privacy_policy_url")

        intro_text = get_text("privacy_notice", language)
        if privacy_url:
            intro_text = intro_text.format(url=privacy_url)
        else:
            intro_text = intro_text.replace(" <a href='{url}'>Политикой конфиденциальности</a>", "")

        keyboard = _get_language_keyboard(available_languages)

        if BANNER_PATH.exists():
            await message.answer_photo(
                photo=FSInputFile(BANNER_PATH),
                caption=intro_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            await message.answer(intro_text, reply_markup=keyboard, parse_mode="HTML")

        await state.set_state(UserStates.choosing_language)
    else:
        # Возвращающийся пользователь — сразу в меню
        async with get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(user_id)
            has_consent = bool(user and user.consent_given_at)

        if not has_consent:
            # Нужно получить согласие
            await _show_privacy_consent(message, language, state)
        else:
            await _show_main_menu(message, language)


async def _show_privacy_consent(message: Message, language: str, state: FSMContext):
    """Показывает экран принятия privacy consent (TG-13)."""
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        privacy_url = await config_repo.get("privacy_policy_url")

    text = get_text("privacy_notice", language)
    if privacy_url:
        text = text.format(url=privacy_url)
    else:
        text = text.replace(" <a href='{url}'>Политикой конфиденциальности</a>.", ".")

    await message.answer(
        text,
        reply_markup=_get_privacy_keyboard(language, privacy_url),
        parse_mode="HTML",
    )
    await state.set_state(UserStates.accepting_privacy)


async def _show_main_menu(message: Message, language: str):
    """Показывает главное меню."""
    from database.repository import ChatRepository
    async with get_session() as session:
        chat_repo = ChatRepository(session)
        active = await chat_repo.get_active_session(message.from_user.id)
        has_history = False
        if active:
            history = await chat_repo.get_session_history(active.id, limit=1)
            has_history = len(history) > 0

    greeting = get_text("greeting", language)

    if BANNER_PATH.exists():
        await message.answer_photo(
            photo=FSInputFile(BANNER_PATH),
            caption=greeting,
            reply_markup=get_main_menu_keyboard(language, has_history=has_history),
        )
    else:
        await message.answer(
            greeting,
            reply_markup=get_main_menu_keyboard(language, has_history=has_history),
        )


@router.callback_query(F.data.startswith("lang_"))
async def choose_language(callback: CallbackQuery, state: FSMContext):
    """REG-06/REG-07: выбор языка из экрана приветствия."""
    language = callback.data.split("_", 1)[1]
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
        has_consent = bool(user.consent_given_at)

    if not has_consent:
        # После выбора языка показываем privacy consent
        await state.set_state(UserStates.accepting_privacy)
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            privacy_url = await config_repo.get("privacy_policy_url")

        text = get_text("privacy_notice", language)
        if privacy_url:
            text = text.format(url=privacy_url)

        try:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=_get_privacy_keyboard(language, privacy_url),
                parse_mode="HTML",
            )
        except Exception:
            await callback.message.answer(
                text,
                reply_markup=_get_privacy_keyboard(language, privacy_url),
                parse_mode="HTML",
            )
    else:
        await state.clear()
        greeting = get_text("greeting", language)
        try:
            await callback.message.edit_caption(
                caption=greeting,
                reply_markup=get_main_menu_keyboard(language, has_history=False),
            )
        except Exception:
            await callback.message.answer(
                greeting,
                reply_markup=get_main_menu_keyboard(language, has_history=False),
            )

    await callback.answer()


@router.callback_query(F.data == "privacy_accept")
async def accept_privacy(callback: CallbackQuery, state: FSMContext):
    """TG-13: пользователь принял privacy consent."""
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "ru"

        # Фиксируем согласие
        from sqlalchemy import update
        from database.models import User
        await session.execute(
            update(User).where(User.id == user_id).values(
                consent_version=PRIVACY_CONSENT_VERSION,
                consent_given_at=datetime.utcnow(),
                consent_channel="telegram",
            )
        )
        await session.commit()

    await state.clear()
    greeting = get_text("greeting", language)

    try:
        await callback.message.edit_caption(
            caption=greeting,
            reply_markup=get_main_menu_keyboard(language, has_history=False),
        )
    except Exception:
        await callback.message.answer(
            greeting,
            reply_markup=get_main_menu_keyboard(language, has_history=False),
        )
    await callback.answer()


@router.callback_query(F.data == "privacy_decline")
async def decline_privacy(callback: CallbackQuery, state: FSMContext):
    """TG-13: пользователь отказался от consent — информируем об ограничениях."""
    user_id = callback.from_user.id
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "ru"

    await state.clear()
    await callback.message.answer(
        "ℹ️ Без принятия политики конфиденциальности функции бота ограничены.\n\n"
        "Используйте /start чтобы попробовать снова.",
    )
    await callback.answer()
