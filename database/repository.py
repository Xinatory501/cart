from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    User,
    Config,
    TrainingMessage,
    ChatHistory,
    ChatSession,
    CaseEvent,
    CsatResponse,
    FloodLog,
    AdminAction,
    Metric,
    AIProvider,
    APIKey
)


def _generate_ticket_code() -> str:
    """Генерирует случайный 6-значный буквенно-цифровой код обращения."""
    return ''.join(random.choices(string.digits, k=6))

class UserRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        normalized = (username or "").strip().lstrip("@")
        if not normalized:
            return None

        result = await self.session.execute(
            select(User).where(func.lower(User.username) == normalized.lower())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str]
    ) -> User:
        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_language(self, user_id: int, language: str):
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(language=language, updated_at=datetime.utcnow())
        )
        await self.session.commit()

    async def update_thread_id(self, user_id: int, thread_id: Optional[int]):
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(thread_id=thread_id, updated_at=datetime.utcnow())
        )
        await self.session.commit()

    async def ban_user(self, user_id: int, duration_seconds: Optional[int] = None):
        ban_until = (
            datetime.utcnow() + timedelta(seconds=duration_seconds)
            if duration_seconds
            else None
        )
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                is_banned=True,
                ban_until=ban_until,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def unban_user(self, user_id: int):
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                is_banned=False,
                ban_until=None,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def is_banned(self, user_id: int) -> bool:
        result = await self.session.execute(
            select(User.is_banned, User.ban_until).where(User.id == user_id)
        )
        row = result.one_or_none()
        if not row:
            return False

        is_banned, ban_until = row
        if is_banned:
            if ban_until and ban_until < datetime.utcnow():
                await self.unban_user(user_id)
                return False
            return True
        return False

    async def set_role(self, user_id: int, role: str):
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(role=role, updated_at=datetime.utcnow())
        )
        await self.session.commit()

    async def is_admin(self, user_id: int) -> bool:
        result = await self.session.execute(
            select(User.role).where(User.id == user_id)
        )
        role = result.scalar_one_or_none()
        return role == "admin"

    async def is_operator(self, user_id: int) -> bool:
        result = await self.session.execute(
            select(User.role).where(User.id == user_id)
        )
        role = result.scalar_one_or_none()
        return role in ("operator", "supervisor", "project_admin", "superadmin", "admin")

    async def has_role(self, user_id: int, *roles: str) -> bool:
        result = await self.session.execute(
            select(User.role).where(User.id == user_id)
        )
        role = result.scalar_one_or_none()
        return role in roles

    async def get_all_admins(self) -> List[User]:
        result = await self.session.execute(
            select(User).where(User.role == "admin")
        )
        return list(result.scalars().all())

    async def get_user_stats(self, user_id: int) -> Dict:
        msg_count = await self.session.execute(
            select(func.count(ChatHistory.id)).where(ChatHistory.user_id == user_id)
        )
        message_count = msg_count.scalar()

        sess_count = await self.session.execute(
            select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
        )
        session_count = sess_count.scalar()

        user = await self.get_by_id(user_id)

        return {
            "message_count": message_count,
            "session_count": session_count,
            "user": user
        }

class ConfigRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> Optional[str]:
        result = await self.session.execute(
            select(Config.value).where(Config.key == key)
        )
        return result.scalar_one_or_none()

    async def set(self, key: str, value: str, description: Optional[str] = None):
        existing = await self.session.execute(
            select(Config).where(Config.key == key)
        )
        if existing.scalar_one_or_none():
            await self.session.execute(
                update(Config)
                .where(Config.key == key)
                .values(value=value, updated_at=datetime.utcnow())
            )
        else:
            config = Config(key=key, value=value, description=description)
            self.session.add(config)
        await self.session.commit()

    async def get_working_hours(self) -> dict:
        """OPS-17: Get per-instance working schedule."""
        return {
            'start': await self.get('working_hours_start') or '09:00',
            'end': await self.get('working_hours_end') or '18:00',
            'timezone': await self.get('working_hours_tz') or 'Europe/Moscow',
            'work_days': await self.get('working_days') or 'Mon-Fri',
            'holiday_mode': await self.get('holiday_mode') or '0',
        }

    async def set_working_hours(self, key: str, value: str) -> None:
        await self.set(f'working_hours_{key}', value)

    async def get_branding(self) -> dict:
        """REG-11: Get branding profile (name, contacts, privacy_url, etc.)"""
        keys = ['brand_name','brand_contacts','brand_privacy_url','brand_support_schedule']
        result = {}
        for key in keys:
            val = await self.get(key)
            result[key] = val or ''
        return result

    async def set_branding(self, key: str, value: str) -> None:
        await self.set(key, value)

    async def bump_profile_version(self) -> str:
        """REG-12: Increment profile config version for audit."""
        import datetime
        version = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        await self.set('profile_version', version)
        return version

    async def delete(self, key: str):
        await self.session.execute(
            delete(Config).where(Config.key == key)
        )
        await self.session.commit()

class TrainingRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_active(self) -> List[TrainingMessage]:
        result = await self.session.execute(
            select(TrainingMessage)
            .where(
                and_(
                    TrainingMessage.is_active == True,
                    TrainingMessage.kb_status == 'approved'
                )
            )
            .order_by(
                TrainingMessage.priority.asc(),
                TrainingMessage.created_at.asc()
            )
        )
        return list(result.scalars().all())

    async def search_relevant(self, query: str, limit: int = 5) -> List[TrainingMessage]:
        """AI-09: Find most relevant KB entries using vector similarity (RAG) with keyword fallback."""
        import json
        import math
        
        # Get all approved entries
        result = await self.session.execute(
            select(TrainingMessage)
            .where(TrainingMessage.kb_status == 'approved', TrainingMessage.is_active == True)
        )
        all_msgs = result.scalars().all()
        
        if not all_msgs:
            return []

        # Try generating embedding for the query
        query_vector = None
        ai_service = None
        try:
            from services.ai_service import AIService
            ai_service = await AIService.get_service()
            if ai_service:
                query_vector = await ai_service.generate_embedding(query)
                # Check if it returned a zero-vector fallback
                if all(v == 0.0 for v in query_vector):
                    query_vector = None
        except Exception as e:
            logger.error("RAG search failed to get AI service/vector: %s. Falling back to keyword search.", e)

        # 1. VECTOR SIMILARITY PATH
        if query_vector:
            scored = []
            for msg in all_msgs:
                msg_vector = None
                
                # Check cache in DB
                if msg.vector_embedding:
                    try:
                        msg_vector = json.loads(msg.vector_embedding)
                    except Exception:
                        msg_vector = None
                        
                # Generate and cache if missing
                if not msg_vector and ai_service:
                    try:
                        msg_vector = await ai_service.generate_embedding(msg.content or "")
                        # Save embedding back to database
                        msg.vector_embedding = json.dumps(msg_vector)
                        self.session.add(msg)
                        await self.session.commit()
                    except Exception as e:
                        logger.error("Failed to generate and cache embedding for msg %d: %s", msg.id, e)
                        msg_vector = None
                
                if msg_vector:
                    # Calculate cosine similarity
                    dot_product = sum(a * b for a, b in zip(query_vector, msg_vector))
                    norm_q = math.sqrt(sum(q * q for q in query_vector))
                    norm_m = math.sqrt(sum(m * m for m in msg_vector))
                    
                    similarity = 0.0
                    if norm_q > 0 and norm_m > 0:
                        similarity = dot_product / (norm_q * norm_m)
                        
                    # Boost by priority
                    priority = getattr(msg, 'priority', 0) or 0
                    score = similarity + (priority * 0.05)
                    scored.append((score, msg))
                    
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                return [msg for _, msg in scored[:limit]]

        # 2. KEYWORD OVERLAP FALLBACK (if vector gen failed)
        query_words = set(query.lower().split())
        scored = []
        for msg in all_msgs:
            content_words = set((msg.content or '').lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                priority = getattr(msg, 'priority', 0) or 0
                score = overlap + (priority * 0.1)
                scored.append((score, msg))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [msg for _, msg in scored[:limit]]

    async def add(self, role: str, content: str, priority: int = 0) -> TrainingMessage:
        msg = TrainingMessage(role=role, content=content, priority=priority, kb_status='draft')
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return msg

    async def approve(self, msg_id: int, reviewer_id: Optional[int] = None):
        await self.session.execute(
            update(TrainingMessage)
            .where(TrainingMessage.id == msg_id)
            .values(kb_status='approved', reviewer_id=reviewer_id, updated_at=datetime.utcnow())
        )
        await self.session.commit()

    async def retire(self, msg_id: int):
        await self.session.execute(
            update(TrainingMessage)
            .where(TrainingMessage.id == msg_id)
            .values(kb_status='retired', is_active=False, updated_at=datetime.utcnow())
        )
        await self.session.commit()

    async def get_by_status(self, status: str) -> List[TrainingMessage]:
        result = await self.session.execute(
            select(TrainingMessage)
            .where(TrainingMessage.kb_status == status)
            .order_by(TrainingMessage.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, msg_id: int):
        await self.session.execute(
            delete(TrainingMessage).where(TrainingMessage.id == msg_id)
        )
        await self.session.commit()

    async def get_all(self) -> List[TrainingMessage]:
        result = await self.session.execute(
            select(TrainingMessage).order_by(TrainingMessage.priority.asc())
        )
        return list(result.scalars().all())

    async def toggle_active(self, msg_id: int):
        result = await self.session.execute(
            select(TrainingMessage).where(TrainingMessage.id == msg_id)
        )
        msg = result.scalar_one_or_none()
        if msg:
            await self.session.execute(
                update(TrainingMessage)
                .where(TrainingMessage.id == msg_id)
                .values(is_active=not msg.is_active)
            )
            await self.session.commit()

    async def update_content(self, msg_id: int, content: str):
        await self.session.execute(
            update(TrainingMessage)
            .where(TrainingMessage.id == msg_id)
            .values(content=content, updated_at=datetime.utcnow())
        )
        await self.session.commit()

    async def update_priority(self, msg_id: int, priority: int):
        await self.session.execute(
            update(TrainingMessage)
            .where(TrainingMessage.id == msg_id)
            .values(priority=priority, updated_at=datetime.utcnow())
        )
        await self.session.commit()

class ChatRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(self, user_id: int, channel: str = "telegram") -> ChatSession:
        """Создаёт новый кейс с уникальным 6-значным тикетом (CASE-01 / TG-03)."""
        # Закрываем предыдущую активную сессию
        await self.session.execute(
            update(ChatSession)
            .where(and_(ChatSession.user_id == user_id, ChatSession.is_active == True))
            .values(is_active=False, ended_at=datetime.utcnow(), case_status="CLOSED")
        )

        # Генерируем уникальный тикет (retry on collision)
        ticket_code = None
        for _ in range(10):
            candidate = _generate_ticket_code()
            existing = await self.session.execute(
                select(ChatSession.id).where(ChatSession.ticket_code == candidate)
            )
            if existing.scalar_one_or_none() is None:
                ticket_code = candidate
                break

        session = ChatSession(
            user_id=user_id,
            ticket_code=ticket_code,
            case_status="NEW",
            channel=channel,
            sla_first_response_deadline=datetime.utcnow() + timedelta(hours=4)
        )
        self.session.add(session)
        await self.session.flush()  # Получаем id до commit

        # Audit trail: первое событие
        event = CaseEvent(
            session_id=session.id,
            event_type="status_change",
            from_value=None,
            to_value="NEW",
            actor_id=user_id,
            actor_role="user",
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(session)
        return session

    async def update_case_status(
        self,
        session_id: int,
        new_status: str,
        actor_id: Optional[int] = None,
        actor_role: str = "system",
        note: Optional[str] = None,
    ):
        """Обновляет статус кейса и добавляет audit event."""
        result = await self.session.execute(
            select(ChatSession.case_status).where(ChatSession.id == session_id)
        )
        old_status = result.scalar_one_or_none()

        values: Dict = {"case_status": new_status}
        if new_status in ("RESOLVED", "CLOSED"):
            values["is_active"] = False
            values["ended_at"] = datetime.utcnow()
        if new_status == "RESOLVED":
            values["resolved_at"] = datetime.utcnow()
        if new_status == "CLOSED":
            values["closed_at"] = datetime.utcnow()

        await self.session.execute(
            update(ChatSession).where(ChatSession.id == session_id).values(**values)
        )

        event = CaseEvent(
            session_id=session_id,
            event_type="status_change",
            from_value=old_status,
            to_value=new_status,
            actor_id=actor_id,
            actor_role=actor_role,
            note=note,
        )
        self.session.add(event)
        await self.session.commit()

    async def set_pinned_message_id(self, session_id: int, message_id: int):
        """Сохраняет ID закреплённого сообщения с тикетом."""
        await self.session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(pinned_message_id=message_id)
        )
        await self.session.commit()

    async def get_session_by_thread_id(self, thread_id: int) -> Optional[ChatSession]:
        result = await self.session.execute(
            select(ChatSession).where(
                ChatSession.support_thread_id == thread_id,
                ChatSession.is_active == True
            ).order_by(ChatSession.started_at.desc())
        )
        return result.scalars().first()

    async def assign_owner(self, session_id: int, owner_id: int):
        await self.session.execute(
            update(ChatSession).where(ChatSession.id == session_id).values(owner_id=owner_id, case_status='IN_PROGRESS')
        )
        event = CaseEvent(
            session_id=session_id,
            event_type="status_change",
            to_value="IN_PROGRESS",
            actor_id=owner_id,
            actor_role="support",
        )
        self.session.add(event)
        await self.session.commit()

    async def get_session_by_ticket(self, ticket_code: str) -> Optional[ChatSession]:
        """Ищет кейс по 6-значному коду тикета."""
        result = await self.session.execute(
            select(ChatSession).where(ChatSession.ticket_code == ticket_code)
        )
        return result.scalar_one_or_none()

    async def get_user_sessions(self, user_id: int, limit: int = 20) -> List[ChatSession]:
        """Возвращает список кейсов пользователя."""
        result = await self.session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def add_csat(
        self,
        session_id: int,
        user_id: int,
        rating: int,
        comment: Optional[str] = None,
        operator_id: Optional[int] = None,
        ai_handled: bool = True,
    ) -> CsatResponse:
        """Сохраняет оценку CSAT после закрытия кейса."""
        existing = await self.session.execute(
            select(CsatResponse).where(CsatResponse.session_id == session_id)
        )
        if existing.scalar_one_or_none():
            return  # Идемпотентность: одна оценка на кейс

        csat = CsatResponse(
            session_id=session_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
            operator_id=operator_id,
            ai_handled=ai_handled,
        )
        self.session.add(csat)
        await self.session.commit()
        await self.session.refresh(csat)
        return csat


    async def get_active_session(self, user_id: int) -> Optional[ChatSession]:
        result = await self.session.execute(
            select(ChatSession)
            .where(and_(ChatSession.user_id == user_id, ChatSession.is_active == True))
        )
        return result.scalar_one_or_none()

    async def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
        message_id: Optional[int] = None,
        is_ai_handled: bool = False,
        media_type: Optional[str] = None,
        file_id: Optional[str] = None
    ) -> ChatHistory:
        session = await self.get_active_session(user_id)
        session_id = session.id if session else None

        msg = ChatHistory(
            user_id=user_id,
            message_id=message_id,
            role=role,
            content=content,
            session_id=session_id,
            is_ai_handled=is_ai_handled,
            media_type=media_type,
            file_id=file_id
        )
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return msg

    async def get_session_history(
        self,
        session_id: int,
        limit: int = 50
    ) -> List[ChatHistory]:
        result = await self.session.execute(
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def deactivate_ai(self, user_id: int):
        session = await self.get_active_session(user_id)
        if session:
            await self.session.execute(
                update(ChatSession)
                .where(ChatSession.id == session.id)
                .values(is_ai_active=False)
            )
            await self.session.commit()

    async def activate_ai(self, user_id: int):
        session = await self.get_active_session(user_id)
        if session:
            await self.session.execute(
                update(ChatSession)
                .where(ChatSession.id == session.id)
                .values(is_ai_active=True)
            )
            await self.session.commit()

class FloodRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_and_update(
        self,
        user_id: int,
        threshold: int,
        time_window: int
    ) -> tuple[bool, int]:
        result = await self.session.execute(
            select(FloodLog).where(FloodLog.user_id == user_id)
        )
        log = result.scalar_one_or_none()

        now = datetime.utcnow()

        if not log:
            log = FloodLog(user_id=user_id, message_count=1, last_message_at=now)
            self.session.add(log)
            await self.session.commit()
            return False, 1

        time_diff = (now - log.last_message_at).total_seconds()

        if time_diff > time_window:
            await self.session.execute(
                update(FloodLog)
                .where(FloodLog.user_id == user_id)
                .values(message_count=1, last_message_at=now)
            )
            await self.session.commit()
            return False, 1

        new_count = log.message_count + 1
        await self.session.execute(
            update(FloodLog)
            .where(FloodLog.user_id == user_id)
            .values(message_count=new_count, last_message_at=now)
        )
        await self.session.commit()

        is_flooding = new_count > threshold
        return is_flooding, new_count

    async def increment_ban_count(self, user_id: int):
        await self.session.execute(
            update(FloodLog)
            .where(FloodLog.user_id == user_id)
            .values(ban_count=FloodLog.ban_count + 1)
        )
        await self.session.commit()

class AdminRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_action(
        self,
        admin_id: int,
        action_type: str,
        target_user_id: Optional[int] = None,
        details: Optional[str] = None
    ):
        action = AdminAction(
            admin_id=admin_id,
            action_type=action_type,
            target_user_id=target_user_id,
            details=details
        )
        self.session.add(action)
        await self.session.commit()

    async def get_user_count_by_period(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> int:
        result = await self.session.execute(
            select(func.count(User.id))
            .where(and_(User.created_at >= start_date, User.created_at <= end_date))
        )
        return result.scalar()

    async def get_message_count_by_period(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> int:
        result = await self.session.execute(
            select(func.count(ChatHistory.id))
            .where(and_(
                ChatHistory.created_at >= start_date,
                ChatHistory.created_at <= end_date
            ))
        )
        return result.scalar()

    async def get_case_stats_by_period(self, start_date: datetime, end_date: datetime) -> dict:
        total = await self.session.scalar(
            select(func.count(ChatSession.id)).where(
                ChatSession.started_at >= start_date,
                ChatSession.started_at <= end_date
            )
        )
        resolved_by_ai = await self.session.scalar(
            select(func.count(ChatSession.id)).where(
                ChatSession.started_at >= start_date,
                ChatSession.started_at <= end_date,
                ChatSession.case_status.in_(['AI_RESOLVED', 'CLOSED']),
                ChatSession.owner_id == None
            )
        )
        avg_csat = await self.session.scalar(
            select(func.avg(CsatResponse.rating)).where(
                CsatResponse.created_at >= start_date,
                CsatResponse.created_at <= end_date
            )
        )
        return {
            'total_cases': total or 0,
            'resolved_by_ai': resolved_by_ai or 0,
            'avg_csat': round(float(avg_csat or 0), 2),
        }

    async def get_questions_by_period(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 1000,
        ai_only: bool = False
    ) -> List[str]:
        conditions = [
            ChatHistory.role == "user",
            ChatHistory.created_at >= start_date,
            ChatHistory.created_at <= end_date,
        ]

        if ai_only:
            conditions.append(ChatHistory.is_ai_handled == True)

        result = await self.session.execute(
            select(ChatHistory.content)
            .where(and_(*conditions))
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
        )

        return [row[0] for row in result.all() if row[0] and row[0].strip()]

    async def get_top_questions(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 100
    ) -> List[Dict]:
        result = await self.session.execute(
            select(ChatHistory.content)
            .where(and_(
                ChatHistory.role == 'user',
                ChatHistory.created_at >= start_date,
                ChatHistory.created_at <= end_date
            ))
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
        )
        questions = [row[0] for row in result.all()]
        return [{"content": q} for q in questions]

class MetricRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        user_id: int,
        metric_type: str,
        value: int = 1,
        extra_data: Optional[str] = None
    ):
        metric = Metric(
            user_id=user_id,
            metric_type=metric_type,
            value=value,
            extra_data=extra_data
        )
        self.session.add(metric)
        await self.session.commit()

class AIProviderRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_default(self) -> Optional[AIProvider]:
        result = await self.session.execute(
            select(AIProvider)
            .where(and_(AIProvider.is_active == True, AIProvider.is_default == True))
            .order_by(AIProvider.priority.desc())
        )
        return result.scalar_one_or_none()

    async def get_all_active(self) -> List[AIProvider]:
        result = await self.session.execute(
            select(AIProvider)
            .where(AIProvider.is_active == True)
            .order_by(AIProvider.priority.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, provider_id: int) -> Optional[AIProvider]:
        result = await self.session.execute(
            select(AIProvider).where(AIProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> List[AIProvider]:
        result = await self.session.execute(
            select(AIProvider).order_by(AIProvider.priority.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        name: str,
        display_name: str,
        
        base_url: Optional[str] = None,
        is_default: bool = False
    ) -> AIProvider:
        if is_default:
            await self.session.execute(
                update(AIProvider).values(is_default=False)
            )

        provider = AIProvider(
            name=name,
            display_name=display_name,
            
            base_url=base_url,
            is_default=is_default
        )
        self.session.add(provider)
        await self.session.commit()
        await self.session.refresh(provider)
        return provider

    async def update(
        self,
        provider_id: int,
        default_model: Optional[str] = None,
        base_url: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_default: Optional[bool] = None,
        priority: Optional[int] = None
    ):
        values = {"updated_at": datetime.utcnow()}

        if default_model is not None:
            values["default_model"] = default_model
        if base_url is not None:
            values["base_url"] = base_url
        if is_active is not None:
            values["is_active"] = is_active
        if priority is not None:
            values["priority"] = priority
        if is_default is not None:
            if is_default:
                await self.session.execute(
                    update(AIProvider).values(is_default=False)
                )
            values["is_default"] = is_default

        await self.session.execute(
            update(AIProvider)
            .where(AIProvider.id == provider_id)
            .values(**values)
        )
        await self.session.commit()

    async def delete(self, provider_id: int):
        await self.session.execute(
            delete(AIProvider).where(AIProvider.id == provider_id)
        )
        await self.session.commit()

class APIKeyRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def normalize_api_key(api_key: Optional[str]) -> str:
        from utils.encryption import decrypt_value
        cleaned = (api_key or "").strip()
        cleaned = decrypt_value(cleaned)

        if cleaned.lower().startswith("bearer "):
            cleaned = cleaned[7:].strip()

        if len(cleaned) >= 2 and (
            (cleaned[0] == '"' and cleaned[-1] == '"') or
            (cleaned[0] == "'" and cleaned[-1] == "'")
        ):
            cleaned = cleaned[1:-1].strip()

        return cleaned

    @staticmethod
    def _is_placeholder_key(api_key: Optional[str]) -> bool:
        cleaned = APIKeyRepository.normalize_api_key(api_key)
        if not cleaned:
            return True

        lowered = cleaned.lower()
        if lowered in {
            "your_api_key_here",
            "changeme",
            "change_me",
            "replace_me",
            "replace-with-real-key",
        }:
            return True

        # Default placeholders created by bootstrap.
        if lowered.startswith("your_") and lowered.endswith("_api_key_here"):
            return True

        return False

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        result = await self.session.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        return result.scalar_one_or_none()

    async def get_by_provider(self, provider_id: int) -> List[APIKey]:
        result = await self.session.execute(
            select(APIKey)
            .where(APIKey.provider_id == provider_id)
            .order_by(APIKey.is_active.desc(), APIKey.created_at)
        )
        return list(result.scalars().all())

    async def get_available_key(self, provider_id: int) -> Optional[APIKey]:
        now = datetime.utcnow()
        rate_limit_cooldown = now - timedelta(seconds=60)
        result = await self.session.execute(
            select(APIKey)
            .where(and_(
                APIKey.provider_id == provider_id,
                APIKey.is_active == True,
                or_(
                    APIKey.requests_limit == None,
                    APIKey.requests_made < APIKey.requests_limit,
                    and_(
                        APIKey.limit_reset_at != None,
                        APIKey.limit_reset_at <= now
                    )
                ),
            ))
            .order_by(APIKey.last_used_at.asc().nullsfirst())
        )
        candidates = list(result.scalars().all())

        placeholders_disabled = False

        for key in candidates:
            if self._is_placeholder_key(key.api_key):
                await self.session.execute(
                    update(APIKey)
                    .where(APIKey.id == key.id)
                    .values(
                        is_active=False,
                        last_error="Placeholder API key disabled automatically",
                        updated_at=now
                    )
                )
                placeholders_disabled = True
                continue

            # Cooldown after any provider error (not only 429) to reduce immediate retries.
            if key.last_error and key.updated_at and key.updated_at > rate_limit_cooldown:
                continue

            if placeholders_disabled:
                await self.session.commit()
            return key

        if placeholders_disabled:
            await self.session.commit()

        return None

    async def deactivate_placeholder_keys(self) -> int:
        now = datetime.utcnow()
        result = await self.session.execute(
            select(APIKey).where(APIKey.is_active == True)
        )
        keys = list(result.scalars().all())

        deactivated = 0
        for key in keys:
            if self._is_placeholder_key(key.api_key):
                await self.session.execute(
                    update(APIKey)
                    .where(APIKey.id == key.id)
                    .values(
                        is_active=False,
                        last_error="Placeholder API key disabled automatically",
                        updated_at=now
                    )
                )
                deactivated += 1

        if deactivated:
            await self.session.commit()

        return deactivated

    async def normalize_existing_keys(self) -> int:
        now = datetime.utcnow()
        result = await self.session.execute(select(APIKey))
        keys = list(result.scalars().all())

        updated = 0
        for key in keys:
            normalized = self.normalize_api_key(key.api_key)
            if normalized != (key.api_key or ""):
                await self.session.execute(
                    update(APIKey)
                    .where(APIKey.id == key.id)
                    .values(api_key=normalized, updated_at=now)
                )
                updated += 1

        if updated:
            await self.session.commit()

        return updated

    async def create(
        self,
        provider_id: int,
        api_key: str,
        name: Optional[str] = None,
        requests_limit: Optional[int] = None
    ) -> APIKey:
        normalized_key = self.normalize_api_key(api_key)
        key = APIKey(
            provider_id=provider_id,
            api_key=normalized_key,
            name=name,
            requests_limit=requests_limit
        )
        self.session.add(key)
        await self.session.commit()
        await self.session.refresh(key)
        return key

    async def update_usage(self, key_id: int, increment: int = 1):
        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(
                requests_made=APIKey.requests_made + increment,
                last_used_at=datetime.utcnow(),
                last_error=None,                                                
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def reset_limit(self, key_id: int, new_reset_time: Optional[datetime] = None):
        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(
                requests_made=0,
                limit_reset_at=new_reset_time,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def set_error(self, key_id: int, error_message: str):
        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(
                last_error=error_message,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def deactivate(self, key_id: int):
        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(
                is_active=False,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def activate(self, key_id: int):
        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(
                is_active=True,
                last_error=None,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def delete(self, key_id: int):
        await self.session.execute(
            delete(APIKey).where(APIKey.id == key_id)
        )
        await self.session.commit()

    async def update_limit(
        self,
        key_id: int,
        requests_limit: Optional[int] = None,
        limit_reset_at: Optional[datetime] = None
    ):
        values = {"updated_at": datetime.utcnow()}
        if requests_limit is not None:
            values["requests_limit"] = requests_limit
        if limit_reset_at is not None:
            values["limit_reset_at"] = limit_reset_at

        await self.session.execute(
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(**values)
        )
        await self.session.commit()

class AIModelRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, model_id: int):
        from database.models import AIModel
        result = await self.session.execute(
            select(AIModel).where(AIModel.id == model_id)
        )
        return result.scalar_one_or_none()

    async def get_by_provider(self, provider_id: int):
        from database.models import AIModel
        result = await self.session.execute(
            select(AIModel)
            .where(AIModel.provider_id == provider_id)
            .order_by(AIModel.is_default.desc(), AIModel.is_active.desc(), AIModel.created_at)
        )
        return list(result.scalars().all())

    async def get_default_model(self, provider_id: int):
        from database.models import AIModel
        result = await self.session.execute(
            select(AIModel)
            .where(and_(
                AIModel.provider_id == provider_id,
                AIModel.is_default == True,
                AIModel.is_active == True
            ))
        )
        return result.scalar_one_or_none()

    async def get_available_model(self, provider_id: int):
        from database.models import AIModel
        default = await self.get_default_model(provider_id)
        if default:
            return default

        result = await self.session.execute(
            select(AIModel)
            .where(and_(
                AIModel.provider_id == provider_id,
                AIModel.is_active == True
            ))
            .order_by(AIModel.last_used_at.asc().nullsfirst())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        provider_id: int,
        model_name: str,
        display_name: Optional[str] = None,
        is_default: bool = False
    ):
        from database.models import AIModel

        if is_default:
            await self.session.execute(
                update(AIModel)
                .where(AIModel.provider_id == provider_id)
                .values(is_default=False)
            )

        model = AIModel(
            provider_id=provider_id,
            model_name=model_name,
            display_name=display_name,
            is_default=is_default
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def set_default(self, model_id: int):
        from database.models import AIModel
        model = await self.get_by_id(model_id)
        if not model:
            return

        await self.session.execute(
            update(AIModel)
            .where(AIModel.provider_id == model.provider_id)
            .values(is_default=False)
        )

        await self.session.execute(
            update(AIModel)
            .where(AIModel.id == model_id)
            .values(is_default=True, updated_at=datetime.utcnow())
        )
        await self.session.commit()

    async def record_error(self, model_id: int, error_message: str):
        from database.models import AIModel
        await self.session.execute(
            update(AIModel)
            .where(AIModel.id == model_id)
            .values(
                last_error=error_message[:500],
                error_count=AIModel.error_count + 1,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def deactivate(self, model_id: int):
        from database.models import AIModel
        await self.session.execute(
            update(AIModel)
            .where(AIModel.id == model_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        await self.session.commit()

    async def activate(self, model_id: int):
        from database.models import AIModel
        await self.session.execute(
            update(AIModel)
            .where(AIModel.id == model_id)
            .values(
                is_active=True,
                last_error=None,
                error_count=0,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.commit()

    async def delete(self, model_id: int):
        from database.models import AIModel
        await self.session.execute(
            delete(AIModel).where(AIModel.id == model_id)
        )
        await self.session.commit()

    async def update_last_used(self, model_id: int):
        from database.models import AIModel
        await self.session.execute(
            update(AIModel)
            .where(AIModel.id == model_id)
            .values(last_used_at=datetime.utcnow(), updated_at=datetime.utcnow())
        )
        await self.session.commit()

class PendingRequestRepository:
    def __init__(self, session):
        self.session = session

    async def create(self, user_id: int, message_text: str, message_id: int, session_id: int):
        from database.models import PendingRequest
        idempotency_key = f"{user_id}_{message_id}_{session_id}"
        existing = await self.session.execute(
            select(PendingRequest).where(PendingRequest.idempotency_key == idempotency_key)
        )
        if existing_record := existing.scalar_one_or_none():
            return existing_record

        pending = PendingRequest(
            user_id=user_id,
            message_text=message_text,
            message_id=message_id,
            session_id=session_id,
            status="pending",
            idempotency_key=idempotency_key
        )
        self.session.add(pending)
        await self.session.commit()
        await self.session.refresh(pending)
        return pending

    async def get_all_pending(self):
        from database.models import PendingRequest
        result = await self.session.execute(
            select(PendingRequest).where(PendingRequest.status == "pending").order_by(PendingRequest.created_at)
        )
        return list(result.scalars().all())

    async def mark_started(self, request_id: int):
        from database.models import PendingRequest
        await self.session.execute(
            update(PendingRequest)
            .where(PendingRequest.id == request_id)
            .values(
                status="processing",
                started_at=datetime.utcnow(),
                attempt_count=PendingRequest.attempt_count + 1
            )
        )
        await self.session.commit()

    async def mark_completed(self, request_id: int):
        from database.models import PendingRequest
        await self.session.execute(
            update(PendingRequest)
            .where(PendingRequest.id == request_id)
            .values(status="completed", completed_at=datetime.utcnow())
        )
        await self.session.commit()

    async def mark_failed(self, request_id: int):
        from database.models import PendingRequest
        await self.session.execute(
            update(PendingRequest)
            .where(PendingRequest.id == request_id)
            .values(status="failed", completed_at=datetime.utcnow())
        )
        await self.session.commit()

    async def delete(self, request_id: int):
        from database.models import PendingRequest
        await self.session.execute(
            delete(PendingRequest).where(PendingRequest.id == request_id)
        )
        await self.session.commit()

class ClarificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        session_id: int,
        original_question: str,
        clarification_question: str,
        options: Optional[str] = None
    ):
        from database.models import ClarificationContext

        await self.session.execute(
            update(ClarificationContext)
            .where(and_(
                ClarificationContext.user_id == user_id,
                ClarificationContext.is_active == True
            ))
            .values(is_active=False)
        )

        context = ClarificationContext(
            user_id=user_id,
            session_id=session_id,
            original_question=original_question,
            clarification_question=clarification_question,
            options=options,
            is_active=True
        )
        self.session.add(context)
        await self.session.commit()
        await self.session.refresh(context)
        return context

    async def get_active(self, user_id: int):
        from database.models import ClarificationContext
        result = await self.session.execute(
            select(ClarificationContext)
            .where(and_(
                ClarificationContext.user_id == user_id,
                ClarificationContext.is_active == True
            ))
            .order_by(ClarificationContext.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def mark_answered(self, context_id: int):
        from database.models import ClarificationContext
        await self.session.execute(
            update(ClarificationContext)
            .where(ClarificationContext.id == context_id)
            .values(is_active=False, answered_at=datetime.utcnow())
        )
        await self.session.commit()

    async def deactivate_all(self, user_id: int):
        from database.models import ClarificationContext
        await self.session.execute(
            update(ClarificationContext)
            .where(and_(
                ClarificationContext.user_id == user_id,
                ClarificationContext.is_active == True
            ))
            .values(is_active=False)
        )
        await self.session.commit()
