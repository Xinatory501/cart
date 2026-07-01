
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import ConfigRepository, AdminRepository
from states.admin_states import AdminStates

router = Router()

@router.callback_query(F.data == "admin_privacy")
async def show_privacy_settings(callback: CallbackQuery):
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        current_url = await config_repo.get("privacy_policy_url") or "Не установлен"

    text = f"""🔒 <b>Политика конфиденциальности</b>

<b>Текущий URL:</b>
<code>{current_url}</code>

Этот URL отображается новым пользователям при первом запуске бота.
"""

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить URL", callback_data="change_privacy_url")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "change_privacy_url")
async def request_new_privacy_url(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🔒 Отправьте новый URL политики конфиденциальности:\n\n"
        "Пример: https://cartame.com/privacy"
    )
    await state.set_state(AdminStates.entering_privacy_url)
    await callback.answer()

@router.message(AdminStates.entering_privacy_url)
async def save_new_privacy_url(message: Message, state: FSMContext):
    new_url = message.text.strip()

    if not new_url.startswith(('http://', 'https://')):
        await message.answer("❌ URL должен начинаться с http:// или https://")
        return

    async with get_session() as session:
        config_repo = ConfigRepository(session)
        admin_repo = AdminRepository(session)

        await config_repo.set("privacy_policy_url", new_url, "URL политики конфиденциальности")
        await admin_repo.log_action(
            message.from_user.id,
            "update_privacy_url",
            details=f"Updated to: {new_url}"
        )

    await message.answer("✅ URL политики конфиденциальности обновлен!")
    await state.clear()
