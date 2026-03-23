
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import TrainingRepository, AdminRepository
from states.admin_states import AdminStates

router = Router()

@router.callback_query(F.data == "admin_training")
async def show_training_messages(callback: CallbackQuery):
    async with get_session() as session:
        training_repo = TrainingRepository(session)
        messages = await training_repo.get_all()

    text = "📚 <b>Обучающие сообщения для AI</b>\n\n"

    if messages:
        text += "Эти сообщения используются как системные промпты для AI:\n\n"
        for i, msg in enumerate(messages, 1):
            status = "✅" if msg.is_active else "❌"
            content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
            text += f"{status} {i}. <code>{content_preview}</code>\n"
            text += f"   Приоритет: {msg.priority}\n\n"
    else:
        text += "Нет обучающих сообщений.\n"

    keyboard = [
        [InlineKeyboardButton(text="Добавить сообщение", callback_data="add_training_msg")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_menu")]
    ]

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "add_training_msg")
async def request_training_message(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📚 Отправьте обучающее сообщение для AI:\n\n"
        "Это будет добавлено в системный промпт и AI будет следовать этим инструкциям.\n\n"
        "Пример:\n"
        "\"При ответах на вопросы о ценах, всегда уточняй у пользователя регион доставки.\""
    )
    await state.set_state(AdminStates.entering_training_message)
    await callback.answer()

@router.message(AdminStates.entering_training_message)
async def save_training_message(message: Message, state: FSMContext):
    content = message.text.strip()

    async with get_session() as session:
        training_repo = TrainingRepository(session)
        admin_repo = AdminRepository(session)

        await training_repo.add(role="system", content=content, priority=0)
        await admin_repo.log_action(
            message.from_user.id,
            "add_training_message",
            details=f"Added: {content[:100]}"
        )

    await message.answer("✅ Обучающее сообщение добавлено!")
    await state.clear()
