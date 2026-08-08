
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
        text += "Выберите сообщение для просмотра и редактирования:\n"
    else:
        text += "Нет обучающих сообщений.\n"

    keyboard = []

    for msg in messages:
        status_badge = ""
        if msg.kb_status == "draft":
            status_badge = "[DRAFT]"
        elif msg.kb_status == "approved":
            status_badge = "[APPROVED]"
        elif msg.kb_status == "retired":
            status_badge = "[RETIRED]"
            
        status = "✅" if msg.is_active else "❌"
        content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
        button_text = f"{status_badge} {status} [ID: {msg.id}] {content_preview}"
        keyboard.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"view_training_{msg.id}"
        )])

    keyboard.append([InlineKeyboardButton(text="➕ Добавить сообщение", callback_data="add_training_msg")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("view_training_"))
async def view_training_message(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        training_repo = TrainingRepository(session)
        messages = await training_repo.get_all()
        msg = next((m for m in messages if m.id == msg_id), None)

        if not msg:
            await callback.answer("Сообщение не найдено", show_alert=True)
            return

    status = "Активно ✅" if msg.is_active else "Неактивно ❌"
    
    status_badge = ""
    if msg.kb_status == "draft":
        status_badge = "[DRAFT] Требует утверждения"
    elif msg.kb_status == "approved":
        status_badge = "[APPROVED] Активно в контексте"
    elif msg.kb_status == "retired":
        status_badge = "[RETIRED] В архиве"

    text = (
        f"📚 <b>Правило Базы знаний #{msg.id}</b>\n\n"
        f"<b>Статус активности:</b> {status}\n"
        f"<b>Статус KB:</b> {status_badge}\n\n"
        f"<b>Содержание:</b>\n"
        f"<code>{msg.content}</code>"
    )

    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить содержание", callback_data=f"edit_training_content_{msg_id}")],
        [InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data=f"toggle_training_{msg_id}")],
    ]
    
    if msg.kb_status != "approved":
        keyboard.append([InlineKeyboardButton(text="✅ Утвердить", callback_data=f"admin_kb_approve_{msg_id}")])
    if msg.kb_status != "retired":
        keyboard.append([InlineKeyboardButton(text="🗃 Архивировать", callback_data=f"admin_kb_retire_{msg_id}")])
        
    keyboard.extend([
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_training_{msg_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_training")]
    ])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_training_content_"))
async def request_edit_content(callback: CallbackQuery, state: FSMContext):
    msg_id = int(callback.data.split("_")[3])
    await state.update_data(editing_training_id=msg_id)
    await state.set_state(AdminStates.editing_training_content)

    await callback.message.answer(
        "✏️ Отправьте новое содержание обучающего сообщения:"
    )
    await callback.answer()

@router.message(AdminStates.editing_training_content)
async def save_edited_content(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("editing_training_id")
    new_content = message.text.strip()

    async with get_session() as session:
        training_repo = TrainingRepository(session)
        admin_repo = AdminRepository(session)

        messages = await training_repo.get_all()
        msg = next((m for m in messages if m.id == msg_id), None)

        if msg:
            await training_repo.update_content(msg_id, new_content)
            await admin_repo.log_action(
                message.from_user.id,
                "edit_training_message",
                details=f"Edited #{msg_id}"
            )

    await message.answer("✅ Содержание обновлено!")
    await state.clear()

@router.callback_query(F.data.startswith("toggle_training_"))
async def toggle_training(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        training_repo = TrainingRepository(session)
        admin_repo = AdminRepository(session)

        await training_repo.toggle_active(msg_id)
        await admin_repo.log_action(
            callback.from_user.id,
            "toggle_training_message",
            details=f"Toggled #{msg_id}"
        )

    await callback.answer("✅ Статус изменен")

    callback.data = f"view_training_{msg_id}"
    await view_training_message(callback)

@router.callback_query(F.data.startswith("delete_training_"))
async def confirm_delete_training(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[2])

    text = "⚠️ <b>Удалить обучающее сообщение?</b>\n\nЭто действие нельзя отменить."

    keyboard = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_training_{msg_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_training_{msg_id}")]
    ]

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_delete_training_"))
async def delete_training(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[3])

    async with get_session() as session:
        training_repo = TrainingRepository(session)
        admin_repo = AdminRepository(session)

        await training_repo.delete(msg_id)
        await admin_repo.log_action(
            callback.from_user.id,
            "delete_training_message",
            details=f"Deleted #{msg_id}"
        )

    await callback.answer("✅ Сообщение удалено", show_alert=True)

    callback.data = "admin_training"
    await show_training_messages(callback)

@router.callback_query(F.data == "add_training_msg")
async def request_training_message(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📚 <b>Добавление обучающего сообщения</b>\n\n"
        "Отправьте текст инструкции для AI.\n\n"
        "<b>Примеры:</b>\n"
        "• При ответах о ценах всегда уточняй регион\n"
        "• Если пользователь спрашивает про карты, уточни какие именно\n"
        "• Всегда предлагай связаться с поддержкой при технических проблемах",
        parse_mode="HTML"
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


@router.callback_query(F.data.startswith("admin_kb_approve_"))
async def approve_training_message(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[3])
    async with get_session() as session:
        training_repo = TrainingRepository(session)
        admin_repo = AdminRepository(session)
        await training_repo.approve(msg_id, reviewer_id=callback.from_user.id)
        await admin_repo.log_action(callback.from_user.id, "approve_training", details=f"Approved #{msg_id}")
    await callback.answer("✅ Правило утверждено", show_alert=True)
    callback.data = f"view_training_{msg_id}"
    await view_training_message(callback)


@router.callback_query(F.data.startswith("admin_kb_retire_"))
async def retire_training_message(callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[3])
    async with get_session() as session:
        training_repo = TrainingRepository(session)
        admin_repo = AdminRepository(session)
        await training_repo.retire(msg_id)
        await admin_repo.log_action(callback.from_user.id, "retire_training", details=f"Retired #{msg_id}")
    await callback.answer("✅ Правило перенесено в архив", show_alert=True)
    callback.data = f"view_training_{msg_id}"
    await view_training_message(callback)
