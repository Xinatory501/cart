from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from database.database import get_session
from database.repository import AdminRepository, UserRepository
from locales.loader import get_text
from services.ai_service import AIService
from services.analytics_service import AnalyticsService
from services.thread_service import ThreadService

router = Router()


@router.callback_query(F.data == "admin_reports")
async def show_reports_menu(callback: CallbackQuery):
    text = """📊 <b>Отчеты и аналитика</b>

Выберите период для генерации отчета:
"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сегодня", callback_data="report_today")],
            [InlineKeyboardButton(text="Последние 7 дней", callback_data="report_week")],
            [InlineKeyboardButton(text="Последние 30 дней", callback_data="report_month")],
            [InlineKeyboardButton(text="Назад", callback_data="admin_menu")],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("report_"))
async def generate_report(callback: CallbackQuery):
    period = callback.data.split("_")[1]
    await callback.answer("⏳ Генерирую отчет...", show_alert=True)

    try:
        analytics = AnalyticsService()
        start_date, end_date = analytics.get_period_dates(period)

        ai_service = await AIService.get_service()

        async with get_session() as session:
            admin_repo = AdminRepository(session)
            report = await analytics.generate_report(
                admin_repo=admin_repo,
                ai_service=ai_service,
                start_date=start_date,
                end_date=end_date,
            )

        await callback.message.answer(report, parse_mode="HTML")

    except Exception as e:
        try:
            thread_service = ThreadService(callback.bot)
            await thread_service.send_log_message(
                f"Report generation failed. admin_id={callback.from_user.id} period={period} error={e}"
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
