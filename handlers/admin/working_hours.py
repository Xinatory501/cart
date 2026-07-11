"""
Admin handlers for working hours configuration.
"""

import json
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from services.working_hours_service import (
    DEFAULT_TIMEZONE,
    get_working_hours_status_text,
    save_config,
    _load_config,
)
from states.admin_states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


# ─── Keyboards ────────────────────────────────────────────────────────────────

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")]]
    )


def _wh_menu_kb(enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data="wh_toggle")],
            [InlineKeyboardButton(text="➕ Добавить смену", callback_data="wh_add_schedule")],
            [InlineKeyboardButton(text="🗑 Удалить смену", callback_data="wh_del_schedule")],
            [InlineKeyboardButton(text="📅 Добавить выходной/праздник", callback_data="wh_add_holiday")],
            [InlineKeyboardButton(text="🗑 Удалить выходной/праздник", callback_data="wh_del_holiday")],
            [InlineKeyboardButton(text="🌐 Изменить часовой пояс", callback_data="wh_set_timezone")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
        ]
    )


def _schedules_del_kb(schedules: list) -> InlineKeyboardMarkup:
    day_short = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
    keyboard = []
    for i, s in enumerate(schedules):
        days_str = ", ".join(day_short.get(d, str(d)) for d in sorted(s.get("days", [])))
        label = f"🗑 {days_str}: {s['start']}–{s['end']}"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"wh_del_sched_{i}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_working_hours")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _holidays_del_kb(holidays: list) -> InlineKeyboardMarkup:
    keyboard = []
    for h in sorted(holidays):
        keyboard.append([InlineKeyboardButton(text=f"🗑 {h}", callback_data=f"wh_del_hol_{h}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_working_hours")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ─── Main working hours menu ───────────────────────────────────────────────────

@router.callback_query(F.data == "admin_working_hours")
async def show_working_hours(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    config = await _load_config()
    text = await get_working_hours_status_text()
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_wh_menu_kb(config.get("enabled", False)),
    )
    await callback.answer()


# ─── Toggle enable/disable ─────────────────────────────────────────────────────

@router.callback_query(F.data == "wh_toggle")
async def toggle_working_hours(callback: CallbackQuery, state: FSMContext):
    config = await _load_config()
    config["enabled"] = not config.get("enabled", False)
    await save_config(config)

    text = await get_working_hours_status_text()
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_wh_menu_kb(config["enabled"]),
    )
    status = "включено ✅" if config["enabled"] else "выключено ❌"
    await callback.answer(f"Время работы {status}")


# ─── Add schedule ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "wh_add_schedule")
async def prompt_add_schedule(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_work_schedule)
    await callback.message.edit_text(
        "➕ <b>Добавить смену</b>\n\n"
        "Введите расписание в формате:\n"
        "<code>1,2,3,4,5 09:00-17:00</code>\n\n"
        "Где цифры — дни недели:\n"
        "0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс\n\n"
        "Пример (будние 9–18):\n"
        "<code>0,1,2,3,4 09:00-18:00</code>",
        parse_mode="HTML",
        reply_markup=_back_kb(),
    )
    await callback.answer()


@router.message(AdminStates.entering_work_schedule)
async def save_schedule(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    # Parse: "1,2,3,4,5 09:00-17:00"
    import re
    match = re.match(r"^([\d,]+)\s+(\d{2}:\d{2})-(\d{2}:\d{2})$", text)
    if not match:
        await message.answer(
            "❌ Неверный формат. Пример: <code>0,1,2,3,4 09:00-18:00</code>",
            parse_mode="HTML",
            reply_markup=_back_kb(),
        )
        return

    days_str, start, end = match.group(1), match.group(2), match.group(3)
    try:
        days = [int(d) for d in days_str.split(",") if d.strip()]
        days = [d for d in days if 0 <= d <= 6]
    except ValueError:
        await message.answer("❌ Дни должны быть числами от 0 до 6.", reply_markup=_back_kb())
        return

    if not days:
        await message.answer("❌ Не указаны корректные дни.", reply_markup=_back_kb())
        return

    if start >= end:
        await message.answer("❌ Время начала должно быть раньше времени окончания.", reply_markup=_back_kb())
        return

    config = await _load_config()
    config.setdefault("schedules", []).append({"days": days, "start": start, "end": end})
    await save_config(config)
    await state.clear()

    text_status = await get_working_hours_status_text()
    await message.answer(
        "✅ Смена добавлена.\n\n" + text_status,
        parse_mode="HTML",
        reply_markup=_wh_menu_kb(config.get("enabled", False)),
    )


# ─── Delete schedule ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "wh_del_schedule")
async def prompt_del_schedule(callback: CallbackQuery, state: FSMContext):
    config = await _load_config()
    schedules = config.get("schedules", [])

    if not schedules:
        await callback.answer("Нет добавленных смен.", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑 <b>Удалить смену</b>\n\nВыберите смену для удаления:",
        parse_mode="HTML",
        reply_markup=_schedules_del_kb(schedules),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wh_del_sched_"))
async def delete_schedule(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[-1])
    config = await _load_config()
    schedules = config.get("schedules", [])

    if 0 <= idx < len(schedules):
        schedules.pop(idx)
        config["schedules"] = schedules
        await save_config(config)
        await callback.answer("✅ Смена удалена")
    else:
        await callback.answer("❌ Смена не найдена")
        return

    text_status = await get_working_hours_status_text()
    await callback.message.edit_text(
        text_status,
        parse_mode="HTML",
        reply_markup=_wh_menu_kb(config.get("enabled", False)),
    )


# ─── Add holiday ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "wh_add_holiday")
async def prompt_add_holiday(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_work_holiday)
    await callback.message.edit_text(
        "📅 <b>Добавить выходной/праздник</b>\n\n"
        "Введите дату в формате <code>ГГГГ-ММ-ДД</code>:\n\n"
        "Примеры:\n"
        "<code>2025-01-01</code> — Новый год\n"
        "<code>2025-05-09</code> — День Победы",
        parse_mode="HTML",
        reply_markup=_back_kb(),
    )
    await callback.answer()


@router.message(AdminStates.entering_work_holiday)
async def save_holiday(message: Message, state: FSMContext):
    import re
    text = (message.text or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        await message.answer(
            "❌ Неверный формат. Введите дату в виде <code>ГГГГ-ММ-ДД</code>",
            parse_mode="HTML",
            reply_markup=_back_kb(),
        )
        return

    config = await _load_config()
    holidays = config.get("holidays", [])
    if text in holidays:
        await message.answer(f"ℹ️ Дата {text} уже добавлена.", reply_markup=_back_kb())
        await state.clear()
        return

    holidays.append(text)
    config["holidays"] = holidays
    await save_config(config)
    await state.clear()

    text_status = await get_working_hours_status_text()
    await message.answer(
        f"✅ Выходной {text} добавлен.\n\n" + text_status,
        parse_mode="HTML",
        reply_markup=_wh_menu_kb(config.get("enabled", False)),
    )


# ─── Delete holiday ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "wh_del_holiday")
async def prompt_del_holiday(callback: CallbackQuery, state: FSMContext):
    config = await _load_config()
    holidays = config.get("holidays", [])

    if not holidays:
        await callback.answer("Нет добавленных выходных.", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑 <b>Удалить выходной/праздник</b>\n\nВыберите дату для удаления:",
        parse_mode="HTML",
        reply_markup=_holidays_del_kb(holidays),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wh_del_hol_"))
async def delete_holiday(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data[len("wh_del_hol_"):]
    config = await _load_config()
    holidays = config.get("holidays", [])

    if date_str in holidays:
        holidays.remove(date_str)
        config["holidays"] = holidays
        await save_config(config)
        await callback.answer(f"✅ {date_str} удалён")
    else:
        await callback.answer("❌ Дата не найдена")
        return

    text_status = await get_working_hours_status_text()
    await callback.message.edit_text(
        text_status,
        parse_mode="HTML",
        reply_markup=_wh_menu_kb(config.get("enabled", False)),
    )


# ─── Set timezone ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "wh_set_timezone")
async def prompt_set_timezone(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_work_timezone)
    await callback.message.edit_text(
        "🌐 <b>Изменить часовой пояс</b>\n\n"
        "Введите название часового пояса в формате IANA:\n\n"
        "Примеры:\n"
        "<code>Europe/Minsk</code>\n"
        "<code>Asia/Almaty</code>\n"
        "<code>Asia/Tashkent</code>\n"
        "<code>Europe/Moscow</code>\n\n"
        f"Текущий: <code>{DEFAULT_TIMEZONE}</code>",
        parse_mode="HTML",
        reply_markup=_back_kb(),
    )
    await callback.answer()


@router.message(AdminStates.entering_work_timezone)
async def save_timezone(message: Message, state: FSMContext):
    tz_str = (message.text or "").strip()
    try:
        import pytz
        pytz.timezone(tz_str)
    except Exception:
        await message.answer(
            f"❌ Неизвестный часовой пояс: <code>{tz_str}</code>\n\n"
            "Используйте формат: <code>Europe/Minsk</code>",
            parse_mode="HTML",
            reply_markup=_back_kb(),
        )
        return

    config = await _load_config()
    config["timezone"] = tz_str
    await save_config(config)
    await state.clear()

    text_status = await get_working_hours_status_text()
    await message.answer(
        f"✅ Часовой пояс установлен: <code>{tz_str}</code>\n\n" + text_status,
        parse_mode="HTML",
        reply_markup=_wh_menu_kb(config.get("enabled", False)),
    )
