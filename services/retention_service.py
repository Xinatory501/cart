from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from database.database import get_session

logger = logging.getLogger(__name__)

# Default retention: 90 days for messages, 365 days for sessions
DEFAULT_MESSAGE_RETENTION_DAYS = 90
DEFAULT_SESSION_RETENTION_DAYS = 365

class RetentionService:
    """
    SEC-05: GDPR/LGPD data retention policy enforcement.
    Runs daily to purge messages older than retention period.
    """
    def __init__(self):
        self._running = False
    
    async def start(self):
        self._running = True
        asyncio.create_task(self._daily_loop())
        logger.info('RetentionService started')
    
    async def _daily_loop(self):
        while self._running:
            try:
                await asyncio.sleep(86400)  # Run once per day
                await self.run_retention()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error('Retention error: %s', e)
    
    async def run_retention(self, message_days: int = DEFAULT_MESSAGE_RETENTION_DAYS,
                             session_days: int = DEFAULT_SESSION_RETENTION_DAYS) -> dict:
        """Purge old messages and close old sessions."""
        from sqlalchemy import delete, update, and_
        from database.models import ChatHistory, ChatSession, CsatResponse
        
        now = datetime.utcnow()
        msg_cutoff = now - timedelta(days=message_days)
        sess_cutoff = now - timedelta(days=session_days)
        
        deleted_msgs = 0
        closed_sessions = 0
        
        async with get_session() as session:
            # Delete old chat messages
            result = await session.execute(
                delete(ChatHistory).where(ChatHistory.created_at < msg_cutoff)
            )
            deleted_msgs = result.rowcount
            
            # Close stale open sessions
            result = await session.execute(
                update(ChatSession)
                .where(and_(
                    ChatSession.is_active == True,
                    ChatSession.started_at < sess_cutoff,
                ))
                .values(is_active=False, case_status='CLOSED')
            )
            closed_sessions = result.rowcount
            
            await session.commit()
        
        logger.info(
            'Retention: deleted %d messages, closed %d sessions (cutoffs: msg=%dd, sess=%dd)',
            deleted_msgs, closed_sessions, message_days, session_days
        )
        return {'deleted_messages': deleted_msgs, 'closed_sessions': closed_sessions}
    
    async def delete_user_data(self, user_id: int) -> dict:
        """
        SEC-05/06: Right to erasure — delete all PII for a user.
        Called by admin for GDPR deletion requests.
        """
        from sqlalchemy import delete, update
        from database.models import ChatHistory, ChatSession, User
        
        async with get_session() as session:
            # Anonymize user record (keep ID for referential integrity)
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    username='[deleted]',
                    first_name='[deleted]',
                    last_name=None,
                    language='ru',
                    is_banned=True,  # Prevent re-registration
                )
            )
            # Delete all chat messages
            await session.execute(
                delete(ChatHistory).where(ChatHistory.user_id == user_id)
            )
            # Close all sessions
            await session.execute(
                update(ChatSession)
                .where(ChatSession.user_id == user_id)
                .values(is_active=False, case_status='DELETED')
            )
            await session.commit()
        
        logger.info('GDPR erasure completed for user %d', user_id)
        return {'user_id': user_id, 'status': 'erased'}
