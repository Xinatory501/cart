import io
import os
from datetime import datetime
from typing import List, Dict

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from database.models import ChatHistory

class ExportService:
    @staticmethod
    def _init_pdf_fonts():
        font_paths = [
            "assets/Arial.ttf",
            "/app/assets/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf"
        ]
        
        registered = False
        for path in font_paths:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont('Arial', path))
                    registered = True
                    break
                except Exception:
                    continue
        
        if not registered:
            pass

    @staticmethod
    def export_to_txt(user_id: int, username: str, messages: List[ChatHistory], session_info: Dict = None) -> str:
        if session_info is None:
            session_info = {}
            
        output = io.StringIO()
        output.write("==================================================\n")
        output.write(f"ЧАТ-ЛОГ ПОЛЬЗОВАТЕЛЯ: {user_id} (@{username or 'не указан'})\n")
        output.write(f"Экспортировано: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
        output.write("==================================================\n\n")

        last_session_id = None
        for msg in messages:
            if msg.session_id and msg.session_id != last_session_id:
                last_session_id = msg.session_id
                info = session_info.get(msg.session_id, {})
                started = info.get("started_at")
                ticket = info.get("ticket_number")
                
                started_str = started.strftime("%d.%m.%Y %H:%M:%S") if started else "неизвестно"
                ticket_str = f"Тикет {ticket}" if ticket else f"Диалог #{msg.session_id}"
                
                output.write("\n==================================================\n")
                output.write(f"🚀 НАЧАЛО НОВОГО ДИАЛОГА: {ticket_str} ({started_str})\n")
                output.write("==================================================\n\n")

            timestamp = msg.created_at.strftime("%d.%m.%Y %H:%M:%S")
            role_map = {
                "user": "СОБЕСЕДНИК",
                "assistant": "ИИ-АССИСТЕНТ",
                "support": "ПОДДЕРЖКА"
            }
            role_name = role_map.get(msg.role, msg.role.upper())
            output.write(f"[{timestamp}] [{role_name}]\n")
            output.write(f"{msg.content}\n")
            output.write("--------------------------------------------------\n")

        return output.getvalue()

    @staticmethod
    def export_to_pdf(user_id: int, username: str, messages: List[ChatHistory], session_info: Dict = None) -> bytes:
        if session_info is None:
            session_info = {}
            
        ExportService._init_pdf_fonts()
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        
        styles = getSampleStyleSheet()
        
        # Styles
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontName='Arial',
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#222222'),
            spaceAfter=5,
            alignment=1
        )
        
        meta_style = ParagraphStyle(
            'MetaStyle',
            parent=styles['Normal'],
            fontName='Arial',
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#666666'),
            spaceAfter=25,
            alignment=1
        )
        
        msg_text_style_user = ParagraphStyle(
            'MsgTextUser',
            parent=styles['Normal'],
            fontName='Arial',
            fontSize=9.5,
            leading=13,
            textColor=colors.white
        )
        
        msg_text_style_other = ParagraphStyle(
            'MsgTextOther',
            parent=styles['Normal'],
            fontName='Arial',
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor('#222222')
        )
        
        msg_meta_style_user = ParagraphStyle(
            'MsgMetaUser',
            parent=styles['Normal'],
            fontName='Arial',
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor('#D1E7FF'),
            spaceAfter=3
        )
        
        msg_meta_style_other = ParagraphStyle(
            'MsgMetaOther',
            parent=styles['Normal'],
            fontName='Arial',
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor('#777777'),
            spaceAfter=3
        )
        
        session_sep_style = ParagraphStyle(
            'SessionSep',
            fontName='Arial',
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor('#555555'),
            alignment=1
        )

        elements = []
        
        elements.append(Paragraph("История переписки", title_style))
        elements.append(Paragraph(
            f"Пользователь: {user_id} ({f'@{username}' if username else 'Имя пользователя не указано'})<br/>"
            f"Всего сообщений: {len(messages)} | Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            meta_style
        ))
        
        last_session_id = None
        for msg in messages:
            # Check for new session boundary to inject a nice separator
            if msg.session_id and msg.session_id != last_session_id:
                last_session_id = msg.session_id
                info = session_info.get(msg.session_id, {})
                started = info.get("started_at")
                ticket = info.get("ticket_number")
                
                started_str = started.strftime("%d.%m.%Y %H:%M") if started else "неизвестно"
                ticket_str = f"Тикет {ticket}" if ticket else f"Диалог #{msg.session_id}"
                
                p_sep = Paragraph(f"🚀 <b>Начало нового диалога: {ticket_str} ({started_str})</b>", session_sep_style)
                sep_table = Table([[p_sep]], colWidths=[500])
                sep_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F2F2F7')),
                    ('TOPPADDING', (0,0), (-1,-1), 6),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('ROUNDEDCORNERS', [4, 4, 4, 4]),
                ]))
                
                elements.append(Spacer(1, 12))
                elements.append(sep_table)
                elements.append(Spacer(1, 10))

            timestamp = msg.created_at.strftime("%d.%m.%Y %H:%M:%S")
            role = msg.role
            
            content_escaped = msg.content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
            
            if role == "user":
                meta_text = f"Собеседник • {timestamp}"
                p_meta = Paragraph(meta_text, msg_meta_style_user)
                p_body = Paragraph(content_escaped, msg_text_style_user)
                
                bubble_table = Table([[p_meta], [p_body]], colWidths=[280])
                bubble_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#007AFF')),
                    ('TOPPADDING', (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('LEFTPADDING', (0,0), (-1,-1), 10),
                    ('RIGHTPADDING', (0,0), (-1,-1), 10),
                    ('ROUNDEDCORNERS', [8, 8, 8, 8]),
                ]))
                
                align_table = Table([[None, bubble_table]], colWidths=[220, 280])
                align_table.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ]))
                elements.append(align_table)
                
            else:
                if role == "assistant":
                    meta_text = f"ИИ Ассистент • {timestamp}"
                    bg_color = colors.HexColor('#E2F6DD')
                else:
                    meta_text = f"Поддержка • {timestamp}"
                    bg_color = colors.HexColor('#F4ECF7')
                    
                p_meta = Paragraph(meta_text, msg_meta_style_other)
                p_body = Paragraph(content_escaped, msg_text_style_other)
                
                bubble_table = Table([[p_meta], [p_body]], colWidths=[280])
                bubble_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), bg_color),
                    ('TOPPADDING', (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('LEFTPADDING', (0,0), (-1,-1), 10),
                    ('RIGHTPADDING', (0,0), (-1,-1), 10),
                    ('ROUNDEDCORNERS', [8, 8, 8, 8]),
                ]))
                
                align_table = Table([[bubble_table, None]], colWidths=[280, 220])
                align_table.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ]))
                elements.append(align_table)
                
            elements.append(Spacer(1, 4))
            
        doc.build(elements)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
