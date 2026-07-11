import re
from pathlib import Path
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import settings
from database.database import get_session
from database.repository import UserRepository, ConfigRepository
from keyboards.admin import get_admin_menu_keyboard
from states.admin_states import AdminStates

router = Router()
_ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"


def _back_to_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")]]
    )


def _support_group_keyboard(current_group_id: Optional[int]) -> InlineKeyboardMarkup:
    keyboard = []
    if current_group_id:
        keyboard.append(
            [InlineKeyboardButton(text="❌ Отключить группу поддержки", callback_data="admin_support_group_disable")]
        )
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _upsert_env_var(key: str, value: Optional[str]) -> None:
    lines = []
    if _ENV_FILE_PATH.exists():
        lines = _ENV_FILE_PATH.read_text(encoding="utf-8").splitlines()

    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    replaced = False
    updated_lines = []

    for line in lines:
        if pattern.match(line):
            replaced = True
            if value is not None:
                updated_lines.append(f"{key}={value}")
            continue
        updated_lines.append(line)

    if not replaced and value is not None:
        updated_lines.append(f"{key}={value}")

    normalized = "\n".join(updated_lines).rstrip()
    if normalized:
        normalized += "\n"

    _ENV_FILE_PATH.write_text(normalized, encoding="utf-8")


def _set_runtime_support_group(group_id: Optional[int]) -> None:
    object.__setattr__(settings, "SUPPORT_GROUP_ID", group_id)


def _parse_support_group_id(raw_value: str) -> Optional[int]:
    value = (raw_value or "").strip()
    if not value:
        return None

    if "t.me/c/" in value:
        match = re.search(r"t\.me/c/(\d+)", value)
        if not match:
            return None
        return int(f"-100{match.group(1)}")

    try:
        parsed = int(value)
    except ValueError:
        return None

    return parsed


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    user_id = message.from_user.id

    is_admin_from_env = user_id in settings.admin_ids

    if not is_admin_from_env:
        async with get_session() as session:
            user_repo = UserRepository(session)
            is_admin_from_db = await user_repo.is_admin(user_id)
            if not is_admin_from_db:
                await message.answer("У вас нет прав администратора.")
                return

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)

        if not user:
            user = await user_repo.create(
                user_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            await user_repo.set_role(user_id, "admin")
            language = "ru"
        else:
            language = user.language

        if user.role != "admin":
            await user_repo.set_role(user_id, "admin")

    admin_text = "👨‍💼 <b>Панель администратора</b>\n\nВыберите раздел:"

    await message.answer(
        admin_text,
        reply_markup=get_admin_menu_keyboard(language),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_menu")
async def back_to_admin_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id

    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        language = user.language if user else "en"

    admin_text = "👨‍💼 <b>Панель администратора</b>\n\nВыберите раздел:"

    await callback.message.edit_text(
        admin_text,
        reply_markup=get_admin_menu_keyboard(language),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_support_group")
async def open_support_group_settings(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_support_group_id)

    current_group = settings.SUPPORT_GROUP_ID
    current_text = f"<code>{current_group}</code>" if current_group else "не настроена"

    text = (
        "👥 <b>Группа поддержки</b>\n\n"
        f"Текущая группа: {current_text}\n\n"
        "Отправьте <b>ID</b> группы, например:\n"
        "<code>-1001234567890</code>\n\n"
        "Или отправьте ссылку на сообщение в теме:\n"
        "<code>https://t.me/c/1234567890/15</code>\n\n"
        "После сохранения значение запишется в <code>.env</code>."
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_support_group_keyboard(current_group),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_support_group_disable")
async def disable_support_group(callback: CallbackQuery, state: FSMContext):
    _upsert_env_var("SUPPORT_GROUP_ID", None)
    _set_runtime_support_group(None)
    await state.clear()

    await callback.message.edit_text(
        "✅ Группа поддержки отключена. Параметр удален из <code>.env</code>.",
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard(),
    )
    await callback.answer("Группа поддержки отключена")


@router.message(AdminStates.entering_support_group_id)
async def save_support_group_id(message: Message, state: FSMContext):
    parsed_group = _parse_support_group_id(message.text)

    if parsed_group is None:
        await message.answer(
            "❌ Неверный формат. Отправьте ID вида <code>-100...</code> или ссылку <code>https://t.me/c/...</code>.",
            parse_mode="HTML",
            reply_markup=_back_to_admin_keyboard(),
        )
        return

    if parsed_group >= 0:
        await message.answer(
            "❌ Для групп нужен отрицательный ID (обычно начинается с <code>-100</code>).",
            parse_mode="HTML",
            reply_markup=_back_to_admin_keyboard(),
        )
        return

    _upsert_env_var("SUPPORT_GROUP_ID", str(parsed_group))
    _set_runtime_support_group(parsed_group)

    await state.clear()

    await message.answer(
        f"✅ Группа поддержки сохранена: <code>{parsed_group}</code>\n"
        "Значение записано в <code>.env</code>.",
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard(),
    )


@router.callback_query(F.data == "admin_welcome_sticker")
async def open_welcome_sticker_settings(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_welcome_sticker)

    current_sticker = None
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        current_sticker = await config_repo.get("welcome_sticker_file_id")

    current_text = f"<code>{current_sticker}</code>" if current_sticker else "не установлен (отправляется стандартный эмодзи 👋)"

    text = (
        "🖼️ <b>Приветственный стикер</b>\n\n"
        f"Текущий ID стикера: {current_text}\n\n"
        "Отправьте мне любой стикер, чтобы установить его в качестве приветственного.\n\n"
        "Чтобы сбросить приветственный стикер и вернуть эмодзи 👋, напишите: <code>/delete_sticker</code>\n"
        "Или напишите <code>/cancel</code> для отмены."
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.entering_welcome_sticker)
async def save_welcome_sticker(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()

    if text == "/cancel":
        await state.clear()
        await message.answer("❌ Настройка отменена.", reply_markup=_back_to_admin_keyboard())
        return

    if text == "/delete_sticker":
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            await config_repo.set("welcome_sticker_file_id", "")
        await state.clear()
        await message.answer("✅ Приветственный стикер успешно удален (возвращен эмодзи 👋).", reply_markup=_back_to_admin_keyboard())
        return

    if not message.sticker:
        await message.answer(
            "❌ Пожалуйста, отправьте именно стикер. Или отправьте <code>/cancel</code> для отмены.",
            parse_mode="HTML",
            reply_markup=_back_to_admin_keyboard()
        )
        return

    sticker_file_id = message.sticker.file_id

    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.set("welcome_sticker_file_id", sticker_file_id)

    await state.clear()
    await message.answer(
        f"✅ Приветственный стикер успешно установлен!\n"
        f"ID: <code>{sticker_file_id}</code>",
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard()
    )


def _photo_storage_keyboard(current_target: str, current_channel_id: Optional[int]) -> InlineKeyboardMarkup:
    keyboard = []
    if current_target == "topic":
        keyboard.append([InlineKeyboardButton(text="🔄 Отдельный канал/группа", callback_data="admin_photo_target_channel")])
    else:
        keyboard.append([InlineKeyboardButton(text="🔄 Топик поддержки (default)", callback_data="admin_photo_target_topic")])
        keyboard.append([InlineKeyboardButton(text="📝 Указать ID канала/группы", callback_data="admin_photo_change_channel_id")])
        
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(F.data == "admin_photo_storage")
async def open_photo_storage_settings(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    
    target = settings.PHOTO_STORAGE_TARGET or "topic"
    channel_id = settings.PHOTO_STORAGE_CHANNEL_ID
    
    target_str = "Топик поддержки (активный тикет)" if target == "topic" else "Отдельный канал/группа"
    channel_str = f"<code>{channel_id}</code>" if channel_id else "не настроен"
    
    text = (
        "💾 <b>Настройка хранилища фото с сайта</b>\n\n"
        f"<b>Текущий тип хранилища:</b> {target_str}\n"
    )
    if target == "channel":
        text += f"<b>ID канала/группы для хранения:</b> {channel_str}\n\n"
        text += "<i>Убедитесь, что бот добавлен в этот канал/группу как администратор и может отправлять туда фото!</i>"
    else:
        text += "\nВсе изображения, загружаемые посетителями сайта, отправляются напрямую в топик активного обращения пользователя."
        
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_photo_storage_keyboard(target, channel_id),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_photo_target_topic")
async def select_photo_target_topic(callback: CallbackQuery):
    _upsert_env_var("PHOTO_STORAGE_TARGET", "topic")
    object.__setattr__(settings, "PHOTO_STORAGE_TARGET", "topic")
    
    import asyncio
    asyncio.create_task(run_photo_migration(callback.bot, "topic", None))
    
    await callback.message.edit_text(
        "✅ Способ хранения изменен на <b>Топик поддержки</b>.\n\n⏳ В фоновом режиме запущена миграция существующих медиа-файлов.",
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard(),
    )
    await callback.answer("Сохранено")


@router.callback_query(F.data == "admin_photo_target_channel")
async def select_photo_target_channel(callback: CallbackQuery):
    _upsert_env_var("PHOTO_STORAGE_TARGET", "channel")
    object.__setattr__(settings, "PHOTO_STORAGE_TARGET", "channel")
    
    if settings.PHOTO_STORAGE_CHANNEL_ID:
        import asyncio
        asyncio.create_task(run_photo_migration(callback.bot, "channel", settings.PHOTO_STORAGE_CHANNEL_ID))
        mig_msg = "\n\n⏳ В фоновом режиме запущена миграция существующих медиа-файлов."
    else:
        mig_msg = ""
        
    await callback.message.edit_text(
        f"✅ Способ хранения изменен на <b>Отдельный канал/группа</b>.\n\nТеперь вам необходимо указать ID канала/группы для хранения.{mig_msg}",
        parse_mode="HTML",
        reply_markup=_photo_storage_keyboard("channel", settings.PHOTO_STORAGE_CHANNEL_ID),
    )
    await callback.answer("Способ изменен")


@router.callback_query(F.data == "admin_photo_change_channel_id")
async def change_photo_channel_id(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_photo_channel_id)
    
    text = (
        "📝 <b>Укажите ID канала/группы для хранения фото</b>\n\n"
        "Отправьте ID канала/группы поддержки, например:\n"
        "<code>-1001234567890</code>\n\n"
        "<i>Обратите внимание: бот должен быть администратором в этом канале/группе!</i>"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.entering_photo_channel_id)
async def save_photo_channel_id(message: Message, state: FSMContext):
    raw_val = message.text.strip()
    try:
        val = int(raw_val)
    except ValueError:
        await message.answer("❌ ID должен быть числом (обычно начинается с -100). Попробуйте еще раз:")
        return
        
    _upsert_env_var("PHOTO_STORAGE_CHANNEL_ID", str(val))
    object.__setattr__(settings, "PHOTO_STORAGE_CHANNEL_ID", val)
    
    if settings.PHOTO_STORAGE_TARGET == "channel":
        import asyncio
        asyncio.create_task(run_photo_migration(message.bot, "channel", val))
        mig_msg = "\n\n⏳ В фоновом режиме запущена миграция существующих медиа-файлов."
    else:
        mig_msg = ""
        
    await state.clear()
    await message.answer(
        f"✅ ID канала/группы успешно изменен на: <code>{val}</code>{mig_msg}",
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard(),
    )


async def run_photo_migration(bot: Bot, new_target: str, new_channel_id: Optional[int]):
    import logging
    mig_logger = logging.getLogger("migration")
    mig_logger.info("Starting photo migration to target %s...", new_target)
    
    from services.thread_service import ThreadService
    thread_service = ThreadService(bot)
    await thread_service.send_log_message(f"⏳ Начата миграция фотографий в новое хранилище ({new_target})...")
    
    count = 0
    errors = 0
    
    import os
    from database.models import Config, ChatHistory, User
    from database.repository import UserRepository
    from aiogram.types import FSInputFile
    
    async with get_session() as session:
        result = await session.execute(
            select(Config).where(Config.key.like("media_file_id:%"))
        )
        configs = list(result.scalars().all())
        user_repo = UserRepository(session)
        
        for config in configs:
            filename = config.key.split("media_file_id:")[-1]
            old_file_id = config.value
            if not old_file_id:
                continue
                
            upload_dir = '/app/data/uploads'
            local_path = os.path.join(upload_dir, filename)
            downloaded = False
            
            # 1. Ensure file exists locally
            if not os.path.exists(local_path):
                try:
                    file_info = await bot.get_file(old_file_id)
                    os.makedirs(upload_dir, exist_ok=True)
                    await bot.download_file(file_info.file_path, local_path)
                    downloaded = True
                except Exception as e:
                    mig_logger.error("Migration: Failed to download %s: %s", filename, e)
                    errors += 1
                    continue
                    
            # 2. Upload to new target
            new_file_id = None
            try:
                if new_target == "channel" and new_channel_id:
                    input_file = FSInputFile(local_path)
                    msg = await bot.send_photo(
                        chat_id=new_channel_id,
                        photo=input_file,
                        caption=f"📝 Фото (миграция: {filename})"
                    )
                    new_file_id = msg.photo[-1].file_id
                elif new_target == "topic":
                    chat_msg = (await session.execute(
                        select(ChatHistory).where(ChatHistory.content.like(f"%{filename}%"))
                    )).scalars().first()
                    
                    if chat_msg:
                        user = await user_repo.get_by_id(chat_msg.user_id)
                        if user:
                            thread_id = await thread_service.ensure_thread_for_user(
                                user_id=chat_msg.user_id,
                                username=user.username,
                                first_name=user.first_name
                            )
                            if thread_id:
                                input_file = FSInputFile(local_path)
                                msg = await bot.send_photo(
                                    chat_id=thread_service.support_group_id,
                                    message_thread_id=thread_id,
                                    photo=input_file,
                                    caption=f"📝 Фото (миграция: {filename})"
                                )
                                new_file_id = msg.photo[-1].file_id
                                
                if new_file_id:
                    config.value = new_file_id
                    session.add(config)
                    await session.commit()
                    count += 1
            except Exception as e:
                mig_logger.error("Migration: Failed to upload %s to %s: %s", filename, new_target, e)
                errors += 1
            finally:
                if downloaded and os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                    except Exception:
                        pass
                        
    await thread_service.send_log_message(
        f"✅ Миграция медиа-файлов завершена.\nУспешно перемещено: {count}\nОшибок: {errors}"
    )


@router.callback_query(F.data == "admin_toggle_translation")
async def show_translation_toggle_page(callback: CallbackQuery):
    from services.translation_service import get_send_both_setting
    
    send_both = await get_send_both_setting()
    current_mode = "Перевод + Оригинал 🇷🇺" if send_both else "Только перевод 🌐"
    
    text = (
        "🌐 <b>Режим перевода ответов оператора</b>\n\n"
        "Этот параметр определяет формат ответа, который отправляется пользователю, если оператор отвечает на нерусское сообщение:\n\n"
        "• <b>Только перевод</b> — пользователь получит исключительно переведенный текст ответа.\n"
        "• <b>Перевод + Оригинал</b> — пользователь получит перевод и оригинальный русский текст оператора под ним.\n\n"
        f"Текущий режим: <b>{current_mode}</b>"
    )
    
    toggle_text = "🔄 Переключить на Только перевод" if send_both else "🔄 Переключить на Перевод + Оригинал"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data="admin_translation_toggle_mode")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")]
        ]
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_translation_toggle_mode")
async def toggle_translation_mode(callback: CallbackQuery):
    from services.translation_service import get_send_both_setting, set_send_both_setting
    
    current_val = await get_send_both_setting()
    new_val = not current_val
    await set_send_both_setting(new_val)
    
    await show_translation_toggle_page(callback)
    await callback.answer("Режим перевода обновлен.")

