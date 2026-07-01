
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import UserRepository, AdminRepository, ChatRepository
from keyboards.admin import get_user_actions_keyboard, get_user_export_keyboard
from states.admin_states import AdminStates
from locales.loader import get_text
from services.export_service import ExportService
from services.thread_service import ThreadService

router = Router()

@router.callback_query(F.data == "admin_user_info")
async def request_user_id(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👤 Введите ID пользователя или @username:"
    )
    await state.set_state(AdminStates.entering_user_id)
    await callback.answer()


@router.callback_query(F.data == "admin_chats_export")
async def request_export_user_id(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📥 <b>Экспорт чатов и API</b>\n\n"
        "Введите 6-значный номер диалога (тикета):",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.entering_export_user_id)
    await callback.answer()


@router.message(AdminStates.entering_export_user_id)
async def show_export_menu_by_input(message: Message, state: FSMContext):
    identifier = message.text.strip().upper()
    
    if identifier.lower() == "/cancel":
        await state.clear()
        await message.answer("❌ Ввод отменен.")
        return
        
    thread_service = ThreadService(message.bot)
    normalized = thread_service._normalize_ticket_number(identifier)
    
    if not normalized:
        await message.answer(
            "❌ Неверный формат. Номер тикета должен состоять ровно из 6 цифр (например, 123456).\n\n"
            "Попробуйте ввести еще раз или напишите /cancel."
        )
        return
        
    user_id = await thread_service.get_user_id_by_ticket_number(normalized)
    if not user_id:
        await message.answer(
            "❌ Диалог с таким номером не найден.\n\n"
            "Попробуйте ввести другой 6-значный тикет или напишите /cancel."
        )
        return
        
    user = None
    session_id = 0
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        
        from database.models import ChatSession
        from sqlalchemy import select
        result = await session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .where(ChatSession.ticket_number == normalized)
        )
        chat_session = result.scalar_one_or_none()
        
        if not chat_session:
            result = await session.execute(
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.started_at.desc())
                .limit(1)
            )
            chat_session = result.scalar_one_or_none()
            
        session_id = chat_session.id if chat_session else 0
        
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден в базе данных.")
        return
        
    await state.clear()
    
    text = (
        f"📥 <b>Экспорт чата и API</b>\n\n"
        f"Диалог: <b>{normalized}</b>\n"
        f"Пользователь: <b>{user.first_name or 'Пользователь'}</b> (ID: <code>{user.id}</code>, @{user.username or 'нет'})\n\n"
        f"Выберите формат для скачивания истории переписки или прочекайте настройки API."
    )
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_user_export_keyboard(user.id, normalized, session_id)
    )

@router.message(AdminStates.entering_user_id)
async def show_user_info(message: Message, state: FSMContext):
    identifier = message.text.strip()

    user_id = None
    username_query = None
    if identifier.startswith("@") or not identifier.isdigit():
        username_query = identifier
    else:
        try:
            user_id = int(identifier)
        except ValueError:
            await message.answer("❌ Некорректный формат ID")
            return

    async with get_session() as session:
        user_repo = UserRepository(session)
        if username_query:
            user = await user_repo.get_by_username(username_query)
            if not user:
                await message.answer("❌ Пользователь не найден")
                await state.clear()
                return
            stats = await user_repo.get_user_stats(user.id)
        else:
            stats = await user_repo.get_user_stats(user_id)

        if not stats['user']:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            return

        user = stats['user']

        info_text = f"""👤 <b>Информация о пользователе</b>

<b>Основное:</b>
• ID: <code>{user.id}</code>
• Username: {f'@{user.username}' if user.username else 'Не указан'}
• Имя: {user.first_name or 'Не указано'} {user.last_name or ''}
• Язык: {user.language}
• Роль: {user.role}

<b>Статистика:</b>
• Сообщений: {stats['message_count']}
• Сессий: {stats['session_count']}

<b>Статус:</b>
• Забанен: {'✅ Да' if user.is_banned else '❌ Нет'}
• Топик ID: {user.thread_id or 'Не создан'}
• Дата регистрации: {user.created_at.strftime('%d.%m.%Y %H:%M')}
"""

        await message.answer(
            info_text,
            reply_markup=get_user_actions_keyboard(
                user.language,
                user.id,
                user.is_banned,
                user.role == "admin"
            ),
            parse_mode="HTML"
        )

    await state.clear()

@router.callback_query(F.data.startswith("admin_ban_"))
async def ban_user(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        user_repo = UserRepository(session)
        admin_repo = AdminRepository(session)

        await user_repo.ban_user(user_id)
        await admin_repo.log_action(
            callback.from_user.id,
            "ban_user",
            target_user_id=user_id
        )

    await callback.answer("✅ Пользователь забанен", show_alert=True)

@router.callback_query(F.data.startswith("admin_unban_"))
async def unban_user(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        user_repo = UserRepository(session)
        admin_repo = AdminRepository(session)

        await user_repo.unban_user(user_id)
        await admin_repo.log_action(
            callback.from_user.id,
            "unban_user",
            target_user_id=user_id
        )

    await callback.answer("✅ Пользователь разбанен", show_alert=True)

@router.callback_query(F.data.startswith("admin_grant_"))
async def grant_admin(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        user_repo = UserRepository(session)
        admin_repo = AdminRepository(session)

        await user_repo.set_role(user_id, "admin")
        await admin_repo.log_action(
            callback.from_user.id,
            "grant_admin",
            target_user_id=user_id
        )

    await callback.answer("✅ Права администратора выданы", show_alert=True)

@router.callback_query(F.data.startswith("admin_revoke_"))
async def revoke_admin(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        user_repo = UserRepository(session)
        admin_repo = AdminRepository(session)

        await user_repo.set_role(user_id, "user")
        await admin_repo.log_action(
            callback.from_user.id,
            "revoke_admin",
            target_user_id=user_id
        )

    await callback.answer("✅ Права администратора отозваны", show_alert=True)

@router.callback_query(F.data.startswith("admin_dl_txt_"))
async def download_chat_txt(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("❌ Устаревшая кнопка. Пожалуйста, откройте меню заново.", show_alert=True)
        return
        
    user_id = int(parts[3])
    target = parts[4]
    
    from database.models import ChatSession
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        admin_repo = AdminRepository(session)
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
            
        sessions_list = await chat_repo.get_user_sessions(user_id)
        session_info = {
            s.id: {
                "started_at": s.started_at,
                "ticket_number": s.ticket_number
            }
            for s in sessions_list
        }
            
        if target == "all":
            messages = await chat_repo.get_all_user_history(user_id)
            caption = f"📝 Вся история переписки пользователя {user_id}"
            filename = f"chat_{user_id}_full.txt"
        else:
            session_id = int(target)
            messages = await chat_repo.get_all_session_history(session_id)
            
            db_sess = await session.get(ChatSession, session_id)
            ticket_suffix = f"_{db_sess.ticket_number}" if db_sess and db_sess.ticket_number else f"_session_{session_id}"
            
            caption = f"📝 История переписки {user_id} (Диалог {ticket_suffix[1:]})"
            filename = f"chat_{user_id}{ticket_suffix}.txt"
            
        if not messages:
            await callback.answer("❌ Выбранный диалог пуст", show_alert=True)
            return
            
        await admin_repo.log_action(
            callback.from_user.id,
            "download_chat_txt",
            target_user_id=user_id,
            details=f"session_id={target}"
        )
        
    await callback.answer("Генерирую TXT файл...")
    txt_content = ExportService.export_to_txt(user.id, user.username, messages, session_info)
    
    txt_bytes = txt_content.encode("utf-8")
    input_file = BufferedInputFile(txt_bytes, filename=filename)
    
    await callback.message.answer_document(
        document=input_file,
        caption=caption
    )

@router.callback_query(F.data.startswith("admin_dl_pdf_"))
async def download_chat_pdf(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("❌ Устаревшая кнопка. Пожалуйста, откройте меню заново.", show_alert=True)
        return
        
    user_id = int(parts[3])
    target = parts[4]
    
    from database.models import ChatSession
    async with get_session() as session:
        user_repo = UserRepository(session)
        chat_repo = ChatRepository(session)
        admin_repo = AdminRepository(session)
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
            
        sessions_list = await chat_repo.get_user_sessions(user_id)
        session_info = {
            s.id: {
                "started_at": s.started_at,
                "ticket_number": s.ticket_number
            }
            for s in sessions_list
        }
            
        if target == "all":
            messages = await chat_repo.get_all_user_history(user_id)
            caption = f"📕 Вся история переписки пользователя {user_id} (PDF)"
            filename = f"chat_{user_id}_full.pdf"
        else:
            session_id = int(target)
            messages = await chat_repo.get_all_session_history(session_id)
            
            db_sess = await session.get(ChatSession, session_id)
            ticket_suffix = f"_{db_sess.ticket_number}" if db_sess and db_sess.ticket_number else f"_session_{session_id}"
            
            caption = f"📕 История переписки {user_id} (Диалог {ticket_suffix[1:]}) (PDF)"
            filename = f"chat_{user_id}{ticket_suffix}.pdf"
            
        if not messages:
            await callback.answer("❌ Выбранный диалог пуст", show_alert=True)
            return
            
        await admin_repo.log_action(
            callback.from_user.id,
            "download_chat_pdf",
            target_user_id=user_id,
            details=f"session_id={target}"
        )
        
    await callback.answer("Генерирую PDF файл...")
    
    try:
        pdf_bytes = ExportService.export_to_pdf(user.id, user.username, messages, session_info)
        input_file = BufferedInputFile(pdf_bytes, filename=filename)
        
        await callback.message.answer_document(
            document=input_file,
            caption=caption
        )
    except Exception as error:
        await callback.message.answer(f"❌ Ошибка генерации PDF: {error}")


@router.callback_query(F.data.startswith("admin_exp_menu_"))
async def open_export_menu(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 6:
        await callback.answer("❌ Устаревшая кнопка. Пожалуйста, откройте меню заново.", show_alert=True)
        return
        
    user_id = int(parts[3])
    ticket_number = parts[4]
    session_id = int(parts[5])
    
    async with get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
        
    text = (
        f"📥 <b>Экспорт чата и API</b>\n\n"
        f"Диалог: <b>{ticket_number}</b>\n"
        f"Пользователь: <b>{user.first_name or 'Пользователь'}</b> (ID: <code>{user.id}</code>, @{user.username or 'нет'})\n\n"
        f"Выберите формат для скачивания истории переписки или прочекайте настройки API."
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_user_export_keyboard(user_id, ticket_number, session_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_api_info_"))
async def show_api_info(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 6:
        await callback.answer("❌ Устаревшая кнопка. Пожалуйста, откройте меню заново.", show_alert=True)
        return
        
    user_id = int(parts[3])
    ticket_number = parts[4]
    session_id = int(parts[5])
    
    text = (
        f"ℹ️ <b>Интеграция по API</b>\n\n"
        f"Вы можете запрашивать переписку пользователя с внешних систем.\n\n"
        f"<b>Запрос:</b>\n"
        f"Метод: <code>GET</code>\n"
        f"URL: <code>http://&lt;IP_сервера&gt;:8080/api/chat/{user_id}</code>\n\n"
        f"<b>Ответ (JSON):</b>\n"
        f"<pre>"
        f"{{\n"
        f"  \"user_id\": {user_id},\n"
        f"  \"username\": \"username\",\n"
        f"  \"first_name\": \"Name\",\n"
        f"  \"messages\": [\n"
        f"    {{\n"
        f"      \"id\": 12,\n"
        f"      \"role\": \"user\",\n"
        f"      \"content\": \"Текст\",\n"
        f"      \"is_ai_handled\": true,\n"
        f"      \"created_at\": \"2026-07-01T17:05:51\"\n"
        f"    }}\n"
        f"  ]\n"
        f"}}"
        f"</pre>"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_exp_menu_{user_id}_{ticket_number}_{session_id}")]
        ]
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "admin_exp_back")
async def back_to_export_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📥 <b>Экспорт чатов и API</b>\n\n"
        "Введите 6-значный номер диалога (тикета):",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.entering_export_user_id)
    await callback.answer()
