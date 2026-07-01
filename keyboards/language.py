from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_language_keyboard(prefix: str = "lang") -> InlineKeyboardMarkup:
    def _cb(code: str) -> str:
        return f"{prefix}_{code}"

    keyboard = [
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data=_cb("en")),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data=_cb("ru")),
        ],
        [
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data=_cb("uz")),
            InlineKeyboardButton(text="🇰🇿 Қазақ", callback_data=_cb("kz")),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
