
from typing import Optional, Union

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


def get_chat_keyboard(language: str, ticket_code: str = None) -> InlineKeyboardMarkup:
    """
    Клавиатура чата/обращения.
    Если передан ticket_code — показывает номер тикета в кнопке.
    Всегда включает кнопку закрытия обращения.
    """
    # Кнопка с номером тикета или просто «Обращение»
    if ticket_code:
        ticket_label = f"🎫 Обращение #{ticket_code}"
    else:
        ticket_label = "🎫 Обращение"

    keyboard = [
        [
            InlineKeyboardButton(
                text=ticket_label,
                callback_data="ticket_info"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Закрыть обращение",
                callback_data="close_case"
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


def get_csat_keyboard(language: str, session_id: Union[int, str]) -> InlineKeyboardMarkup:
    """
    Клавиатура оценки качества поддержки (CSAT).
    Звёзды 1–5 в двух рядах: [1⭐ 2⭐ 3⭐] и [4⭐ 5⭐].
    Кнопка «Пропустить» в отдельном ряду.
    callback_data формат: csat_{session_id}_{rating}
    """
    row1 = [
        InlineKeyboardButton(text="1⭐", callback_data=f"csat_{session_id}_1"),
        InlineKeyboardButton(text="2⭐", callback_data=f"csat_{session_id}_2"),
        InlineKeyboardButton(text="3⭐", callback_data=f"csat_{session_id}_3"),
    ]
    row2 = [
        InlineKeyboardButton(text="4⭐", callback_data=f"csat_{session_id}_4"),
        InlineKeyboardButton(text="5⭐", callback_data=f"csat_{session_id}_5"),
    ]
    row3 = [
        InlineKeyboardButton(
            text=get_text("csat_skip", language),
            callback_data="menu_back"
        )
    ]

    return InlineKeyboardMarkup(inline_keyboard=[row1, row2, row3])
