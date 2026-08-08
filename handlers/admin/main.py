from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select, update  # ADM-18 fix: добавлены недостающие импорты


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


@router.callback_query(F.data == 'admin_config')
async def admin_config_menu(callback: CallbackQuery):
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        support_group = await config_repo.get('support_group_id') or settings.SUPPORT_GROUP_ID or 'не задана'
        working_start = await config_repo.get('working_hours_start') or '09:00'
        working_end = await config_repo.get('working_hours_end') or '18:00'
    
    text = (
        f'⚙️ <b>Конфигурация экземпляра</b>\n\n'
        f'Группа поддержки: <code>{support_group}</code>\n'
        f'Рабочие часы: {working_start} — {working_end}\n'
        f'Регион: {settings.REGION_CODE}\n'
        f'Тип проекта: {getattr(settings, "PROJECT_TYPE", "BUSINESS")}\n'
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📞 Группа поддержки', callback_data='admin_set_support_group')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='admin_menu')],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()

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


@router.callback_query(F.data == "admin_set_support_group")
async def open_support_group_settings(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_support_group_id)

    async with get_session() as session:
        config_repo = ConfigRepository(session)
        current_group = await config_repo.get('support_group_id') or settings.SUPPORT_GROUP_ID
        
    current_text = f"<code>{current_group}</code>" if current_group else "не настроена"

    text = (
        "👥 <b>Группа поддержки</b>\n\n"
        f"Текущая группа: {current_text}\n\n"
        "Отправьте <b>ID</b> группы, например:\n"
        "<code>-1001234567890</code>\n\n"
        "Или отправьте ссылку на сообщение в теме:\n"
        "<code>https://t.me/c/1234567890/15</code>\n\n"
        "После сохранения значение запишется в базу данных."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отключить", callback_data="admin_support_group_disable")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_config")]
    ])
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "admin_support_group_disable")
async def disable_support_group(callback: CallbackQuery, state: FSMContext):
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.delete("support_group_id")
    _set_runtime_support_group(None)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_config")]
    ])
    await callback.message.edit_text(
        "✅ Группа поддержки отключена.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer("Группа поддержки отключена")


@router.message(AdminStates.entering_support_group_id)
async def save_support_group_id(message: Message, state: FSMContext):
    parsed_group = _parse_support_group_id(message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_config")]
    ])

    if parsed_group is None:
        await message.answer(
            "❌ Неверный формат. Отправьте ID вида <code>-100...</code> или ссылку <code>https://t.me/c/...</code>.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    if parsed_group >= 0:
        await message.answer(
            "❌ Для групп нужен отрицательный ID (обычно начинается с <code>-100</code>).",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.set("support_group_id", str(parsed_group))
    _set_runtime_support_group(parsed_group)

    await state.clear()

    await message.answer(
        f"✅ Группа поддержки сохранена: <code>{parsed_group}</code>\n"
        "Значение записано в базу данных.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "admin_system_prompt")
async def open_system_prompt_settings(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_base_system_prompt)

    async with get_session() as session:
        config_repo = ConfigRepository(session)
        current_prompt = await config_repo.get("base_system_prompt")

    if not current_prompt:
        current_prompt = "Используется встроенный промпт по умолчанию (посмотрите в services/ai_service.py)."

    text = (
        "✏️ <b>Настройка базового системного промпта</b>\n\n"
        "Текущий промпт:\n"
        f"<code>{current_prompt}</code>\n\n"
        "Отправьте новый системный промпт для нейросети.\n\n"
        "<i>Подсказка: Вы можете использовать плейсхолдеры <code>{language}</code> для автоподстановки кода языка пользователя (например, ru, kz, uz) и <code>{description}</code> для описания сервиса.</i>\n\n"
        "Для сброса к дефолтному отправьте слово: <code>default</code>"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.entering_base_system_prompt)
async def save_base_system_prompt(message: Message, state: FSMContext):
    new_prompt = message.text.strip()

    async with get_session() as session:
        config_repo = ConfigRepository(session)

        if new_prompt.lower() == "default":
            await config_repo.delete("base_system_prompt")
            response_text = "✅ Системный промпт сброшен к значению по умолчанию."
        else:
            await config_repo.set("base_system_prompt", new_prompt, description="Base system prompt for AI")
            response_text = "✅ Базовый системный промпт сохранен!"

    await state.clear()
    await message.answer(
        response_text,
        reply_markup=_back_to_admin_keyboard()
    )
@router.callback_query(F.data == "admin_critical_chat")
async def open_critical_chat_settings(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_critical_chat_id)
    
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        current_chat_id = await config_repo.get("critical_alert_chat_id")
        
    current_text = f"<code>{current_chat_id}</code>" if current_chat_id else "не настроен"
    
    text = (
        "🚨 <b>Чат для критических P1 алертов</b>\n\n"
        f"Текущий чат: {current_text}\n\n"
        "Отправьте <b>ID</b> чата для срочных уведомлений (например <code>-100...</code>)\n"
        "Для отключения отправьте: <code>disable</code>"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_back_to_admin_keyboard(),
    )
    await callback.answer()

@router.message(AdminStates.entering_critical_chat_id)
async def save_critical_chat_id(message: Message, state: FSMContext):
    val = message.text.strip()
    
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        if val.lower() == "disable":
            await config_repo.delete("critical_alert_chat_id")
            resp = "✅ Критические алерты отключены."
        else:
            await config_repo.set("critical_alert_chat_id", val, description="Chat ID for P1 critical alerts")
            resp = f"✅ Чат для P1 алертов сохранен: <code>{val}</code>"
            
    await state.clear()
    await message.answer(resp, parse_mode="HTML", reply_markup=_back_to_admin_keyboard())

@router.callback_query(F.data == "admin_branding")
async def admin_branding(callback: CallbackQuery, state: FSMContext):
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        branding = await config_repo.get_branding()

    text = (
        "🏷️ <b>Брендирование (Профиль)</b>\n\n"
        f"<b>Название:</b> {branding.get('brand_name') or 'Не задано'}\n"
        f"<b>Контакты:</b> {branding.get('brand_contacts') or 'Не задано'}\n"
        f"<b>Privacy URL:</b> {branding.get('brand_privacy_url') or 'Не задано'}\n"
        f"<b>График работы:</b> {branding.get('brand_support_schedule') or 'Не задано'}\n"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data="brand_edit_name")],
        [InlineKeyboardButton(text="✏️ Контакты", callback_data="brand_edit_contacts")],
        [InlineKeyboardButton(text="✏️ Privacy URL", callback_data="brand_edit_privacy_url")],
        [InlineKeyboardButton(text="✏️ График", callback_data="brand_edit_schedule")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("brand_edit_"))
async def brand_edit_callback(callback: CallbackQuery, state: FSMContext):
    field = callback.data.replace("brand_edit_", "")
    state_map = {
        "name": AdminStates.entering_brand_name,
        "contacts": AdminStates.entering_brand_contacts,
        "privacy_url": AdminStates.entering_brand_privacy_url,
        "schedule": AdminStates.entering_brand_schedule
    }
    await state.set_state(state_map[field])
    await callback.message.edit_text(f"Введите новое значение для {field}:", reply_markup=_back_to_admin_keyboard())
    await callback.answer()

async def save_branding_value(message: Message, state: FSMContext, key: str):
    val = message.text.strip()
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.set_branding(key, val)
        await config_repo.bump_profile_version()
    await state.clear()
    await message.answer(f"✅ Значение сохранено.", reply_markup=_back_to_admin_keyboard())

@router.message(AdminStates.entering_brand_name)
async def save_brand_name(message: Message, state: FSMContext):
    await save_branding_value(message, state, "brand_name")

@router.message(AdminStates.entering_brand_contacts)
async def save_brand_contacts(message: Message, state: FSMContext):
    await save_branding_value(message, state, "brand_contacts")

@router.message(AdminStates.entering_brand_privacy_url)
async def save_brand_privacy_url(message: Message, state: FSMContext):
    await save_branding_value(message, state, "brand_privacy_url")

@router.message(AdminStates.entering_brand_schedule)
async def save_brand_schedule(message: Message, state: FSMContext):
    await save_branding_value(message, state, "brand_support_schedule")

@router.callback_query(F.data == "admin_languages")
async def admin_languages(callback: CallbackQuery, state: FSMContext):
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        langs = await config_repo.get("instance_languages")
        if not langs:
            langs = settings.INSTANCE_LANGUAGES

    text = (
        "🌐 <b>Языки</b>\n\n"
        f"Текущие языки: {langs}\n\n"
        "Отправьте новый список языков через запятую (например: ru, kk, en)."
    )
    await state.set_state(AdminStates.entering_languages)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_back_to_admin_keyboard())
    await callback.answer()

@router.message(AdminStates.entering_languages)
async def save_languages(message: Message, state: FSMContext):
    val = message.text.strip()
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.set("instance_languages", val)
        await config_repo.bump_profile_version()
    
    settings.INSTANCE_LANGUAGES = val
    _upsert_env_var("INSTANCE_LANGUAGES", val)
    
    await state.clear()
    await message.answer(f"✅ Языки сохранены: {val}", reply_markup=_back_to_admin_keyboard())

@router.callback_query(F.data == "admin_schedule")
async def admin_schedule_menu(callback: CallbackQuery, state: FSMContext):
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        schedule = await config_repo.get_working_hours()

    text = (
        "🕐 <b>График работы (SLA)</b>\n\n"
        f"<b>Время начала:</b> {schedule.get('start')}\n"
        f"<b>Время окончания:</b> {schedule.get('end')}\n"
        f"<b>Часовой пояс:</b> {schedule.get('timezone')}\n"
        f"<b>Рабочие дни:</b> {schedule.get('work_days')}\n"
        f"<b>Режим выходных:</b> {'Включен 🚨' if schedule.get('holiday_mode') == '1' else 'Выключен ☕'}\n"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Время начала", callback_data="schedule_edit_start")],
        [InlineKeyboardButton(text="✏️ Время окончания", callback_data="schedule_edit_end")],
        [InlineKeyboardButton(text="✏️ Часовой пояс", callback_data="schedule_edit_timezone")],
        [InlineKeyboardButton(text="✏️ Рабочие дни", callback_data="schedule_edit_work_days")],
        [InlineKeyboardButton(text="🔄 Переключить режим выходных", callback_data="schedule_toggle_holiday")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("schedule_edit_"))
async def schedule_edit_callback(callback: CallbackQuery, state: FSMContext):
    field = callback.data.replace("schedule_edit_", "")
    await state.update_data(schedule_field=field)
    await state.set_state(AdminStates.entering_schedule_value)
    
    prompts = {
        "start": "Введите время начала работы (например: 09:00):",
        "end": "Введите время окончания работы (например: 18:00):",
        "timezone": "Введите часовой пояс (например: Europe/Minsk или Asia/Almaty):",
        "work_days": "Введите рабочие дни (например: Mon-Fri или Mon-Sat):",
    }
    prompt = prompts.get(field, "Введите новое значение:")
    await callback.message.edit_text(prompt, reply_markup=_back_to_admin_keyboard())
    await callback.answer()


@router.message(AdminStates.entering_schedule_value)
async def save_schedule_value(message: Message, state: FSMContext):
    val = message.text.strip()
    data = await state.get_data()
    field = data.get("schedule_field", "start")
    
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.set_working_hours(field, val)
        await config_repo.bump_profile_version()
        
    await state.clear()
    await message.answer("✅ График работы обновлен.", reply_markup=_back_to_admin_keyboard())

@router.callback_query(F.data == "schedule_toggle_holiday")
async def schedule_toggle_holiday(callback: CallbackQuery, state: FSMContext):
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        current = await config_repo.get("working_hours_holiday_mode")
        new_val = "1" if current == "0" or not current else "0"
        await config_repo.set_working_hours("holiday_mode", new_val)
        await config_repo.bump_profile_version()
    
    await admin_schedule_menu(callback, state)
