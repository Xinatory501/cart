
from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
import os

from database.database import get_session
from database.repository import UserRepository
from locales.loader import get_text
from services.backup_service import BackupService
from services.thread_service import ThreadService

router = Router()

@router.callback_query(F.data == "admin_database")
async def show_database_menu(callback: CallbackQuery):
    text = """💾 <b>Работа с базой данных</b>

<b>Доступные операции:</b>
• Скачать бекап - создает копию текущей БД
• Загрузить бекап - восстанавливает БД из файла

⚠️ <b>Внимание:</b> При восстановлении текущая БД будет заменена!
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Скачать бекап", callback_data="download_backup")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "download_backup")
async def download_backup(callback: CallbackQuery):
    await callback.answer("⏳ Создаю бекап...", show_alert=True)

    try:
        backup_service = BackupService()
        backup_path = await backup_service.create_backup()

        file = FSInputFile(backup_path)
        await callback.message.answer_document(
            file,
            caption="💾 Бекап базы данных создан успешно"
        )

        if os.path.exists(backup_path):
            os.remove(backup_path)

        await callback.answer("✅ Бекап отправлен!", show_alert=True)

    except Exception as e:
        try:
            thread_service = ThreadService(callback.bot)
            await thread_service.send_log_message(
                f"Database backup failed. admin_id={callback.from_user.id} error={e}"
            )
        except Exception:
            pass

        language = "en"
        async with get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(callback.from_user.id)
            if user:
                language = user.language

        await callback.answer(get_text("error_try_later", language), show_alert=True)
