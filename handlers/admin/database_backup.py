
from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
import os
import shutil

from database.database import get_session
from database.repository import UserRepository
from locales.loader import get_text
from services.backup_service import BackupService
from services.thread_service import ThreadService
from states.admin_states import AdminStates

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
        [InlineKeyboardButton(text="📥 Скачать бекап", callback_data="download_backup")],
        [InlineKeyboardButton(text="📤 Загрузить бекап", callback_data="upload_backup")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu")]
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

@router.callback_query(F.data == "upload_backup")
async def request_backup_upload(callback: CallbackQuery, state: FSMContext):
    text = """📤 <b>Загрузка бекапа базы данных</b>

⚠️ <b>ВНИМАНИЕ!</b>
• Текущая база данных будет полностью заменена
• Все текущие данные будут потеряны
• Бот будет перезапущен после восстановления

Отправьте файл бекапа (.db) для восстановления.

Для отмены отправьте /cancel"""

    await callback.message.answer(text, parse_mode="HTML")
    await state.set_state(AdminStates.uploading_backup)
    await callback.answer()

@router.message(AdminStates.uploading_backup, F.document)
async def handle_backup_upload(message: Message, state: FSMContext):
    document = message.document

    if not document.file_name.endswith('.db'):
        await message.answer(
            "❌ Неверный формат файла!\n\n"
            "Отправьте файл с расширением .db"
        )
        return

    await message.answer("⏳ Загружаю и проверяю файл...")

    try:
        file = await message.bot.get_file(document.file_id)
        temp_path = f"/tmp/restore_{message.from_user.id}.db"

        await message.bot.download_file(file.file_path, temp_path)

        if not os.path.exists(temp_path):
            raise Exception("Failed to download file")

        file_size = os.path.getsize(temp_path)
        if file_size < 1024:
            os.remove(temp_path)
            await message.answer("❌ Файл слишком маленький, возможно поврежден")
            return

        text = f"""✅ <b>Файл загружен успешно</b>

<b>Информация:</b>
• Имя файла: {document.file_name}
• Размер: {file_size / 1024:.2f} KB

⚠️ <b>Подтвердите восстановление</b>
Текущая база данных будет заменена!"""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить восстановление", callback_data=f"confirm_restore_{message.from_user.id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_restore")]
        ])

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)

        try:
            thread_service = ThreadService(message.bot)
            await thread_service.send_log_message(
                f"Backup upload failed. admin_id={message.from_user.id} error={e}"
            )
        except Exception:
            pass

        await message.answer(
            "❌ Ошибка при загрузке файла\n\n"
            "Проверьте файл и попробуйте снова"
        )

@router.callback_query(F.data.startswith("confirm_restore_"))
async def confirm_restore(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[2])
    temp_path = f"/tmp/restore_{user_id}.db"

    if not os.path.exists(temp_path):
        await callback.answer("❌ Файл не найден, загрузите заново", show_alert=True)
        await state.clear()
        return

    await callback.answer("⏳ Восстанавливаю базу данных...", show_alert=True)

    try:
        from config import settings
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")

        backup_current = f"{db_path}.backup_before_restore"
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_current)

        shutil.copy2(temp_path, db_path)
        os.remove(temp_path)

        try:
            thread_service = ThreadService(callback.bot)
            await thread_service.send_log_message(
                f"✅ Database restored successfully by admin {user_id}\n"
                f"Previous DB backed up to: {backup_current}"
            )
        except Exception:
            pass

        await callback.message.edit_text(
            "✅ <b>База данных восстановлена успешно!</b>\n\n"
            "Предыдущая версия сохранена как резервная копия.\n"
            "Бот продолжает работу с новой базой данных.",
            parse_mode="HTML"
        )

        await state.clear()

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)

        try:
            thread_service = ThreadService(callback.bot)
            await thread_service.send_log_message(
                f"❌ Database restore failed. admin_id={user_id} error={e}"
            )
        except Exception:
            pass

        await callback.message.edit_text(
            "❌ <b>Ошибка при восстановлении базы данных</b>\n\n"
            f"Детали: {str(e)[:200]}",
            parse_mode="HTML"
        )

        await state.clear()

@router.callback_query(F.data == "cancel_restore")
async def cancel_restore(callback: CallbackQuery, state: FSMContext):
    temp_path = f"/tmp/restore_{callback.from_user.id}.db"
    if os.path.exists(temp_path):
        os.remove(temp_path)

    await callback.message.edit_text("❌ Восстановление отменено")
    await state.clear()
    await callback.answer()

@router.message(AdminStates.uploading_backup, F.text == "/cancel")
async def cancel_upload(message: Message, state: FSMContext):
    temp_path = f"/tmp/restore_{message.from_user.id}.db"
    if os.path.exists(temp_path):
        os.remove(temp_path)

    await message.answer("❌ Загрузка отменена")
    await state.clear()
