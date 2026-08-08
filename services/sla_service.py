from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

from database.database import get_session
from database.repository import ChatRepository

logger = logging.getLogger(__name__)

# SLA config: minutes for first response by priority
SLA_FIRST_RESPONSE_MINUTES = {
    "P1": 30,
    "P2": 120,
    "P3": 480,  # 8 hours
    "P4": 1440,  # 24 hours
    "default": 240,  # 4 hours
}

class SLAService:
    def __init__(self, bots: list):
        self.bots = bots  
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._check_loop())
        logger.info("SLA service started")

    async def _check_loop(self):
        while self._running:
            try:
                await self._check_sla_breaches()
            except Exception as e:
                logger.error("SLA check error: %s", e)
            await asyncio.sleep(300)  # Check every 5 minutes

    async def _check_sla_breaches(self):
        from sqlalchemy import select, and_
        from database.models import ChatSession
        from config import settings
        
        now = datetime.utcnow()
        
        async with get_session() as session:
            # Find active cases with SLA deadline approaching or breached
            result = await session.execute(
                select(ChatSession).where(
                    and_(
                        ChatSession.is_active == True,
                        ChatSession.case_status.in_(['NEW', 'QUEUED', 'IN_PROGRESS']),
                        ChatSession.sla_first_response_deadline != None,
                    )
                )
            )
            cases = result.scalars().all()
        
        for case in cases:
            if case.sla_first_response_deadline:
                time_left = (case.sla_first_response_deadline - now).total_seconds()
                
                if time_left < 0 and not case.sla_breached:
                    # SLA breached
                    await self._notify_sla_breach(case)
                elif 0 < time_left < 1800 and not case.sla_warning_sent:
                    # 30 minutes warning
                    await self._notify_sla_warning(case)

    async def _notify_sla_breach(self, case):
        from config import settings
        from sqlalchemy import update
        from database.models import ChatSession
        
        logger.warning("SLA breached for case %s (ticket %s)", case.id, case.ticket_code)
        
        async with get_session() as session:
            await session.execute(
                update(ChatSession).where(ChatSession.id == case.id).values(sla_breached=True)
            )
            await session.commit()
        
        if settings.SUPPORT_GROUP_ID and case.support_thread_id and self.bots:
            bot = self.bots[0]
            try:
                await bot.send_message(
                    chat_id=settings.SUPPORT_GROUP_ID,
                    message_thread_id=case.support_thread_id,
                    text=f"⏰ <b>SLA НАРУШЕН!</b>\n\nОбращение #{case.ticket_code or case.id} превысило время ответа.\n\nТребуется немедленная реакция!",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error("Failed to send SLA breach notification: %s", e)

    async def _notify_sla_warning(self, case):
        from config import settings
        from sqlalchemy import update
        from database.models import ChatSession
        
        async with get_session() as session:
            await session.execute(
                update(ChatSession).where(ChatSession.id == case.id).values(sla_warning_sent=True)
            )
            await session.commit()
        
        if settings.SUPPORT_GROUP_ID and case.support_thread_id and self.bots:
            bot = self.bots[0]
            try:
                await bot.send_message(
                    chat_id=settings.SUPPORT_GROUP_ID,
                    message_thread_id=case.support_thread_id,
                    text=f"⚠️ <b>SLA предупреждение</b>\n\nОбращение #{case.ticket_code or case.id} — до нарушения SLA осталось менее 30 минут!",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error("Failed to send SLA warning: %s", e)


def set_case_sla(case_session, priority: str = None):
    """Sets SLA deadline on a new case session based on priority."""
    minutes = SLA_FIRST_RESPONSE_MINUTES.get(priority or "default", 240)
    case_session.sla_first_response_deadline = datetime.utcnow() + timedelta(minutes=minutes)
    return case_session
