
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import ConfigRepository, AdminRepository
from states.admin_states import AdminStates

router = Router()

@router.callback_query(F.data == "admin_antiflood")
async def show_antiflood_settings(callback: CallbackQuery):
    async with get_session() as session:
        config_repo = ConfigRepository(session)

        threshold = await config_repo.get("antiflood_threshold") or "1"
        time_window = await config_repo.get("antiflood_time_window") or "3"
        autoban_duration = await config_repo.get("autoban_duration") or "900"

    text = f"""⚡ <b>Настройки антифлуда</b>

<b>Текущие параметры:</b>
• Порог сообщений: {threshold}
• Временное окно: {time_window} сек
• Длительность автобана: {int(autoban_duration) // 60} мин ({autoban_duration} сек)

<b>Как работает:</b>
Если пользователь отправит больше {threshold} сообщений за {time_window} секунд, он будет автоматически забанен на {int(autoban_duration) // 60} минут.
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить порог", callback_data="change_antiflood_threshold")],
        [InlineKeyboardButton(text="Изменить временное окно", callback_data="change_antiflood_window")],
        [InlineKeyboardButton(text="Изменить длительность бана", callback_data="change_autoban_duration")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "change_antiflood_threshold")
async def request_threshold(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🔢 Отправьте новый порог сообщений (число от 1 до 10):\n\n"
        "Пример: 1 (разрешено 1 сообщение за временное окно)"
    )
    await state.set_state(AdminStates.entering_antiflood_threshold)
    await callback.answer()

@router.message(AdminStates.entering_antiflood_threshold)
async def save_threshold(message: Message, state: FSMContext):
    try:
        threshold = int(message.text.strip())
        if threshold < 1 or threshold > 10:
            await message.answer("❌ Порог должен быть от 1 до 10")
            return

        async with get_session() as session:
            config_repo = ConfigRepository(session)
            admin_repo = AdminRepository(session)

            await config_repo.set("antiflood_threshold", str(threshold), "Порог сообщений для антифлуда")
            await admin_repo.log_action(
                message.from_user.id,
                "update_antiflood_threshold",
                details=f"Set to: {threshold}"
            )

        await message.answer(f"✅ Порог антифлуда обновлен: {threshold}")
        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, отправьте число")

@router.callback_query(F.data == "change_antiflood_window")
async def request_time_window(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "⏱ Отправьте новое временное окно в секундах (от 1 до 60):\n\n"
        "Пример: 3 (пользователь не может отправить больше N сообщений за 3 секунды)"
    )
    await state.set_state(AdminStates.entering_antiflood_window)
    await callback.answer()

@router.message(AdminStates.entering_antiflood_window)
async def save_time_window(message: Message, state: FSMContext):
    try:
        time_window = int(message.text.strip())
        if time_window < 1 or time_window > 60:
            await message.answer("❌ Временное окно должно быть от 1 до 60 секунд")
            return

        async with get_session() as session:
            config_repo = ConfigRepository(session)
            admin_repo = AdminRepository(session)

            await config_repo.set("antiflood_time_window", str(time_window), "Временное окно для антифлуда в секундах")
            await admin_repo.log_action(
                message.from_user.id,
                "update_antiflood_window",
                details=f"Set to: {time_window} seconds"
            )

        await message.answer(f"✅ Временное окно обновлено: {time_window} сек")
        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, отправьте число")

@router.callback_query(F.data == "change_autoban_duration")
async def request_autoban_duration(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "⏰ Отправьте новую длительность автобана в секундах:\n\n"
        "Примеры:\n"
        "• 900 = 15 минут\n"
        "• 1800 = 30 минут\n"
        "• 3600 = 1 час"
    )
    await state.set_state(AdminStates.entering_autoban_duration)
    await callback.answer()

@router.message(AdminStates.entering_autoban_duration)
async def save_autoban_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
        if duration < 60 or duration > 86400:
            await message.answer("❌ Длительность должна быть от 60 до 86400 секунд (1 минута - 24 часа)")
            return

        async with get_session() as session:
            config_repo = ConfigRepository(session)
            admin_repo = AdminRepository(session)

            await config_repo.set("autoban_duration", str(duration), "Длительность автобана в секундах")
            await admin_repo.log_action(
                message.from_user.id,
                "update_autoban_duration",
                details=f"Set to: {duration} seconds ({duration // 60} minutes)"
            )

        await message.answer(f"✅ Длительность автобана обновлена: {duration // 60} минут ({duration} сек)")
        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, отправьте число")
