"""
Экспорт истории диалога по 6-значному коду тикета.
ADM-13: TXT и PDF выгрузка с визуализацией (клиент / AI / поддержка).
ADM-14: базовая анонимизация — псевдонимизация идентификаторов.
"""
import io
import logging
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, Message
)
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import ChatRepository, UserRepository
from states.admin_states import AdminStates

logger = logging.getLogger(__name__)
router = Router()

# ---------- Helpers ----------

def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")]]
    )


def _export_format_keyboard(ticket_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 TXT", callback_data=f"export_txt_{ticket_code}"),
            InlineKeyboardButton(text="📄 TXT (аноним)", callback_data=f"export_txt_anon_{ticket_code}")
        ],
        [
            InlineKeyboardButton(text="📑 PDF", callback_data=f"export_pdf_{ticket_code}"),
            InlineKeyboardButton(text="📑 PDF (аноним)", callback_data=f"export_pdf_anon_{ticket_code}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_export_menu")],
    ])


def _role_label(role: str, is_ai_handled: bool) -> str:
    if role == "user":
        return "👤 Клиент"
    if role == "assistant":
        return "🤖 AI-ассистент" if is_ai_handled else "💬 Поддержка"
    if role == "system":
        return "⚙️ Система"
    return f"[{role}]"


def _format_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return dt.strftime("%d.%m.%Y %H:%M")

import hashlib
def _anonymize_text(content: str, user_id: int = None) -> str:
    """Pseudonymize PII: phones, emails, card numbers, usernames."""
    import re
    # Phone numbers (various formats)
    content = re.sub(r'\+?[7-9][\d\s\-\(\)]{9,14}', '[PHONE]', content)
    # Email addresses  
    content = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', '[EMAIL]', content)
    # Card numbers (4 groups of 4 digits)
    content = re.sub(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b', '[CARD]', content)
    # Telegram usernames
    content = re.sub(r'@[\w]{4,}', '[USER]', content)
    # Loyalty IDs (8+ digit sequences)
    content = re.sub(r'\b\d{8,}\b', '[ID]', content)
    return content


def _build_txt(session, messages, anonymize: bool = False) -> str:
    lines = [
        "=" * 60,
        f"ИСТОРИЯ ОБРАЩЕНИЯ #{session.ticket_code or 'N/A'}",
        f"Статус: {session.case_status}",
        f"Открыто: {_format_dt(session.started_at)}",
        f"Закрыто: {_format_dt(session.ended_at or session.closed_at)}",
        "=" * 60,
        "",
    ]
    for msg in messages:
        label = _role_label(msg.role, msg.is_ai_handled)
        ts = _format_dt(msg.created_at)
        content = msg.content or ""
        if anonymize:
            content = _anonymize_text(content, msg.user_id)
        lines.append(f"[{ts}] {label}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def _build_pdf_bytes(session, messages, anonymize: bool = False) -> bytes:
    """
    Генерирует PDF с визуализацией диалога.
    Использует reportlab если установлен, иначе возвращает TXT как байты.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.units import mm

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=20*mm, rightMargin=20*mm,
            topMargin=20*mm, bottomMargin=20*mm
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title', parent=styles['Heading1'],
            fontSize=14, spaceAfter=6
        )
        meta_style = ParagraphStyle(
            'Meta', parent=styles['Normal'],
            fontSize=9, textColor=HexColor('#666666'), spaceAfter=4
        )
        user_style = ParagraphStyle(
            'User', parent=styles['Normal'],
            fontSize=10, backColor=HexColor('#E3F2FD'),
            borderPadding=6, spaceAfter=4
        )
        ai_style = ParagraphStyle(
            'AI', parent=styles['Normal'],
            fontSize=10, backColor=HexColor('#F3E5F5'),
            borderPadding=6, spaceAfter=4
        )
        support_style = ParagraphStyle(
            'Support', parent=styles['Normal'],
            fontSize=10, backColor=HexColor('#E8F5E9'),
            borderPadding=6, spaceAfter=4
        )

        story = [
            Paragraph(f"История обращения #{session.ticket_code or 'N/A'}", title_style),
            Paragraph(f"Статус: {session.case_status} | Открыто: {_format_dt(session.started_at)}", meta_style),
            Paragraph(f"Закрыто: {_format_dt(session.ended_at or session.closed_at)}", meta_style),
            HRFlowable(width="100%", thickness=1, color=HexColor('#CCCCCC'), spaceAfter=8),
        ]

        for msg in messages:
            content = (msg.content or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if anonymize:
                content = _anonymize_text(content, msg.user_id)

            label = _role_label(msg.role, msg.is_ai_handled)
            ts = _format_dt(msg.created_at)
            text = f"<b>{label}</b> <font size='8' color='grey'>{ts}</font><br/>{content}"

            if msg.role == "user":
                style = user_style
            elif msg.role == "assistant" and msg.is_ai_handled:
                style = ai_style
            else:
                style = support_style

            story.append(Paragraph(text, style))
            story.append(Spacer(1, 2*mm))

        doc.build(story)
        return buffer.getvalue()

    except ImportError:
        # Fallback: TXT в байтах если reportlab не установлен
        txt = _build_txt(session, messages, anonymize)
        return txt.encode("utf-8")


# ---------- Handlers ----------

@router.callback_query(F.data == "admin_export_menu")
async def show_export_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_export_ticket)
    await callback.message.edit_text(
        "📁 <b>Экспорт истории диалога</b>\n\n"
        "Введите <b>6-значный код обращения</b> для экспорта:\n"
        "<code>Например: 123456</code>",
        parse_mode="HTML",
        reply_markup=_back_keyboard(),
    )
    await callback.answer()


@router.message(AdminStates.entering_export_ticket)
async def handle_export_ticket_input(message: Message, state: FSMContext):
    ticket_code = (message.text or "").strip()

    if len(ticket_code) != 6 or not ticket_code.isdigit():
        await message.answer(
            "❌ Неверный формат. Введите 6-значный числовой код.",
            reply_markup=_back_keyboard(),
        )
        return

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        case_session = await chat_repo.get_session_by_ticket(ticket_code)

    if not case_session:
        await message.answer(
            f"❌ Обращение <code>{ticket_code}</code> не найдено.",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
        return

    await state.clear()
    await message.answer(
        f"✅ Обращение <code>{ticket_code}</code> найдено.\n\n"
        f"Статус: <b>{case_session.case_status}</b>\n"
        f"Открыто: <b>{_format_dt(case_session.started_at)}</b>\n\n"
        "Выберите формат экспорта:",
        parse_mode="HTML",
        reply_markup=_export_format_keyboard(ticket_code),
    )


@router.callback_query(F.data.startswith("export_txt_"))
async def export_txt(callback: CallbackQuery):
    ticket_code = callback.data.replace("export_txt_", "")
    await callback.answer("⏳ Генерирую TXT...")

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        case_session = await chat_repo.get_session_by_ticket(ticket_code)
        if not case_session:
            await callback.message.answer("❌ Обращение не найдено.")
            return
        messages = await chat_repo.get_session_history(case_session.id, limit=500)

    txt_content = _build_txt(case_session, messages, anonymize=False)
    file_bytes = txt_content.encode("utf-8")

    await callback.message.answer_document(
        document=BufferedInputFile(
            file_bytes,
            filename=f"case_{ticket_code}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        ),
        caption=f"📄 История обращения #{ticket_code}",
    )


@router.callback_query(F.data.startswith("export_pdf_"))
async def export_pdf(callback: CallbackQuery):
    ticket_code = callback.data.replace("export_pdf_", "")
    await callback.answer("⏳ Генерирую PDF...")

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        case_session = await chat_repo.get_session_by_ticket(ticket_code)
        if not case_session:
            await callback.message.answer("❌ Обращение не найдено.")
            return
        messages = await chat_repo.get_session_history(case_session.id, limit=500)

    try:
        pdf_bytes = _build_pdf_bytes(case_session, messages, anonymize=False)

        await callback.message.answer_document(
            document=BufferedInputFile(
                pdf_bytes,
                filename=f"case_{ticket_code}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            ),
            caption=f"📑 История обращения #{ticket_code}",
        )
    except Exception as e:
        logger.error("PDF generation failed for ticket %s: %s", ticket_code, e)
        await callback.message.answer(
            f"❌ Ошибка генерации PDF: {e}\n\nПопробуйте экспорт в TXT.",
        )


@router.callback_query(F.data.startswith("export_txt_anon_"))
async def export_txt_anon(callback: CallbackQuery):
    ticket_code = callback.data.replace("export_txt_anon_", "")
    await callback.answer("⏳ Генерирую TXT (аноним)...")

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        case_session = await chat_repo.get_session_by_ticket(ticket_code)
        if not case_session:
            await callback.message.answer("❌ Обращение не найдено.")
            return
        messages = await chat_repo.get_session_history(case_session.id, limit=500)

    txt_content = _build_txt(case_session, messages, anonymize=True)
    file_bytes = txt_content.encode("utf-8")

    await callback.message.answer_document(
        document=BufferedInputFile(
            file_bytes,
            filename=f"case_{ticket_code}_anon_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        ),
        caption=f"📄 История обращения #{ticket_code} (аноним)",
    )


@router.callback_query(F.data.startswith("export_pdf_anon_"))
async def export_pdf_anon(callback: CallbackQuery):
    ticket_code = callback.data.replace("export_pdf_anon_", "")
    await callback.answer("⏳ Генерирую PDF (аноним)...")

    async with get_session() as session:
        chat_repo = ChatRepository(session)
        case_session = await chat_repo.get_session_by_ticket(ticket_code)
        if not case_session:
            await callback.message.answer("❌ Обращение не найдено.")
            return
        messages = await chat_repo.get_session_history(case_session.id, limit=500)

    try:
        pdf_bytes = _build_pdf_bytes(case_session, messages, anonymize=True)

        await callback.message.answer_document(
            document=BufferedInputFile(
                pdf_bytes,
                filename=f"case_{ticket_code}_anon_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            ),
            caption=f"📑 История обращения #{ticket_code} (аноним)",
        )
    except Exception as e:
        logger.error("PDF generation failed for ticket %s: %s", ticket_code, e)
        await callback.message.answer(
            f"❌ Ошибка генерации PDF: {e}\n\nПопробуйте экспорт в TXT.",
        )
