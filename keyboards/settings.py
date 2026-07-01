
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from locales.loader import get_text

def get_settings_keyboard(language: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text("change_language", language),
                callback_data="settings_language"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("back_to_menu", language),
                callback_data="menu_back"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
