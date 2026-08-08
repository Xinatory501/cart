from __future__ import annotations
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_admin_menu_keyboard(language: str) -> InlineKeyboardMarkup:
    del language
    keyboard = [
        [InlineKeyboardButton(text="🔑 Управление API ключами", callback_data="admin_api_keys")],
        [InlineKeyboardButton(text="⚙️ Конфигурация", callback_data="admin_config")],
        [InlineKeyboardButton(text="🕐 График работы", callback_data="admin_schedule")],
        [InlineKeyboardButton(text="🛡 Настройки антифлуда", callback_data="admin_antiflood")],
        [InlineKeyboardButton(text="🔒 Политика конфиденциальности", callback_data="admin_privacy")],
        [InlineKeyboardButton(text="📚 База знаний (ИИ)", callback_data="admin_training")],
        [InlineKeyboardButton(text="✏️ Системный промпт", callback_data="admin_system_prompt")],
        [InlineKeyboardButton(text="💾 База данных", callback_data="admin_database")],
        [InlineKeyboardButton(text="🚨 P1 Alerts Chat", callback_data="admin_critical_chat")],
        [InlineKeyboardButton(text="📁 Экспорт обращений", callback_data="admin_export_menu")],  # ADM-13
        [InlineKeyboardButton(text="👤 Информация о пользователе", callback_data="admin_user_info")],
        [InlineKeyboardButton(text="👥 Управление ролями", callback_data="admin_roles")],
        [InlineKeyboardButton(text="📊 Отчеты", callback_data="admin_reports")],
        [InlineKeyboardButton(text="🏷️ Брендирование (Профиль)", callback_data="admin_branding")],
        [InlineKeyboardButton(text="🌐 Языки", callback_data="admin_languages")],
        [InlineKeyboardButton(text="🕐 График работы", callback_data="admin_schedule")],
        [InlineKeyboardButton(text="🏠 Назад в меню", callback_data="menu_back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_user_actions_keyboard(language: str, user_id: int, is_banned: bool, is_admin: bool) -> InlineKeyboardMarkup:
    del language
    keyboard = []

    if is_banned:
        keyboard.append([InlineKeyboardButton(text="Разбанить", callback_data=f"admin_unban_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton(text="Забанить", callback_data=f"admin_ban_{user_id}")])

    if is_admin:
        keyboard.append([InlineKeyboardButton(text="Снять админа", callback_data=f"admin_revoke_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton(text="Выдать админа", callback_data=f"admin_grant_{user_id}")])

    keyboard.append([InlineKeyboardButton(text="🗑 Удалить данные (GDPR)", callback_data=f"admin_gdpr_delete_{user_id}")])

    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="admin_menu")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
