
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from locales.loader import get_text

def get_main_menu_keyboard(language: str, has_history: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(
            text=get_text("new_chat", language),
            callback_data="menu_new_chat"
        )],
    ]

    if has_history:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("continue_chat", language),
                callback_data="menu_continue_chat"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text=get_text("settings", language),
            callback_data="menu_settings"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_chat_keyboard(language: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text("back_to_menu", language),
                callback_data="menu_back"
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_try_ai_again_keyboard(language: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text("try_ai_again", language),
                callback_data="try_ai_again"
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
