from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_menu_keyboard(language: str) -> InlineKeyboardMarkup:
    del language
    keyboard = [
        [InlineKeyboardButton(text="🔑 Управление API ключами", callback_data="admin_api_keys")],
        [InlineKeyboardButton(text="👥 Группа поддержки", callback_data="admin_support_group")],
        [InlineKeyboardButton(text="🛡 Настройки антифлуда", callback_data="admin_antiflood")],
        [InlineKeyboardButton(text="🔒 Политика конфиденциальности", callback_data="admin_privacy")],
        [InlineKeyboardButton(text="📚 Обучающие сообщения", callback_data="admin_training")],
        [InlineKeyboardButton(text="💾 База данных", callback_data="admin_database")],
        [InlineKeyboardButton(text="👤 Информация о пользователе", callback_data="admin_user_info")],
        [InlineKeyboardButton(text="📊 Отчеты", callback_data="admin_reports")],
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

    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="admin_menu")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
