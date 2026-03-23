
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import UserRepository, AdminRepository
from keyboards.admin import get_user_actions_keyboard
from states.admin_states import AdminStates
from locales.loader import get_text

router = Router()

@router.callback_query(F.data == "admin_user_info")
async def request_user_id(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👤 Введите ID пользователя или @username:"
    )
    await state.set_state(AdminStates.entering_user_id)
    await callback.answer()

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
