import re
from pathlib import Path
from typing import Optional

from aiogram import F, Router
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
