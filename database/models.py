from __future__ import annotations
"""
Модели базы данных CartaMe Bot.
Версия: 2.0 — добавлена система кейсов (тикетов), SLA, CSAT, KB lifecycle, consent.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    BigInteger, Boolean, Integer, String, Text, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # PII
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # PII
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # PII
    language: Mapped[str] = mapped_column(String(10), default="ru")
    role: Mapped[str] = mapped_column(String(20), default="user")  # user/operator/supervisor/project_admin/superadmin
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    thread_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # PII
    # Согласие на обработку данных
    consent_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    consent_given_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consent_channel: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    chat_history: Mapped[List["ChatHistory"]] = relationship(back_populates="user")
    chat_sessions: Mapped[List["ChatSession"]] = relationship(back_populates="user")


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrainingMessage(Base):
    """База знаний (KB). Поддерживает lifecycle: draft → approved → retired."""
    __tablename__ = "training_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # KB Lifecycle (ADM-09)
    kb_status: Mapped[str] = mapped_column(String(20), default="approved")  # draft/approved/retired
    kb_version: Mapped[int] = mapped_column(Integer, default=1)
    locale: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # ru/kk/uz/en
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reviewer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    superseded_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vector_embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI-09: JSON serialized list of floats
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    """Сессия / Кейс поддержки. Центральная сущность системы обращений."""
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    # Тикет — уникальный 6-значный код обращения (уникален в рамках экземпляра)
    ticket_code: Mapped[Optional[str]] = mapped_column(String(6), nullable=True, unique=True, index=True)

    # Статус кейса (ТЗ раздел 5.3)
    # NEW / AI_PROCESSING / WAITING_USER / AI_RESOLVED / QUEUED /
    # IN_PROGRESS / ESCALATED / RESOLVED / CLOSED / CLOSED_TIMEOUT / REOPENED
    case_status: Mapped[str] = mapped_column(String(30), default="NEW")

    # Приоритет: P1 / P2 / P3 / P4
    priority: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    # Оператор, которому назначен кейс
    owner_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Причина закрытия / решения
    resolution_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Категория обращения
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Канал (telegram / web)
    channel: Mapped[str] = mapped_column(String(20), default="telegram")

    # Версия согласия пользователя на момент создания кейса
    consent_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # SLA дедлайн первого ответа
    sla_first_response_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    sla_warning_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # ID темы в Telegram support supergroup (одна тема = один кейс)
    support_thread_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ID закреплённого сообщения с тикет-кодом (для отмены закрепления при закрытии)
    pinned_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Состояние AI
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_ai_active: Mapped[bool] = mapped_column(Boolean, default=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[List["ChatHistory"]] = relationship(back_populates="session")
    events: Mapped[List["CaseEvent"]] = relationship(back_populates="session")
    csat: Mapped[Optional["CsatResponse"]] = relationship(back_populates="session", uselist=False)


class CaseEvent(Base):
    """Audit trail каждого перехода статуса кейса."""
    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id"))
    event_type: Mapped[str] = mapped_column(String(50))  # status_change / priority_change / assign / escalate
    from_value: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    to_value: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    actor_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="events")


class CsatResponse(Base):
    """CSAT — оценка качества после закрытия кейса."""
    __tablename__ = "csat_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id"), unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # PII
    operator_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    ai_handled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="csat")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)  # PII
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("chat_sessions.id"), nullable=True
    )
    is_ai_handled: Mapped[bool] = mapped_column(Boolean, default=True)
    media_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # ADM-18
    file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # ADM-18
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="chat_history")
    session: Mapped[Optional["ChatSession"]] = relationship(back_populates="messages")


class FloodLog(Base):
    __tablename__ = "flood_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    message_count: Mapped[int] = mapped_column(Integer, default=1)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ban_count: Mapped[int] = mapped_column(Integer, default=0)


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    action_type: Mapped[str] = mapped_column(String(50))
    target_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    before_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    after_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    metric_type: Mapped[str] = mapped_column(String(50))
    value: Mapped[int] = mapped_column(Integer, default=1)
    extra_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AIProvider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    api_keys: Mapped[List["APIKey"]] = relationship(back_populates="provider", cascade="all, delete-orphan")
    models: Mapped[List["AIModel"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_providers.id"))
    api_key: Mapped[str] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    requests_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    limit_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    provider: Mapped["AIProvider"] = relationship(back_populates="api_keys")


class AIModel(Base):
    __tablename__ = "ai_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_providers.id"))
    model_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    provider: Mapped["AIProvider"] = relationship(back_populates="models")


class PendingRequest(Base):
    __tablename__ = "pending_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # Надёжное восстановление (AI-08)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ClarificationContext(Base):
    __tablename__ = "clarification_contexts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    original_question: Mapped[str] = mapped_column(Text, nullable=False)
    clarification_question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Region(Base):
    """Региональный профиль (BY, KZ, UZ) (CT-P0-07)"""
    __tablename__ = "regions"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)  # BY, KZ, UZ
    name: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    languages: Mapped[str] = mapped_column(String(100), default="ru")  # comma-separated
    allowed_project_types: Mapped[str] = mapped_column(String(100), default="BUSINESS")  # comma-separated
    data_policy: Mapped[str] = mapped_column(String(50), default="LOCAL")  # GDPR, LGPD, LOCAL
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProjectProfile(Base):
    """Шаблон конфигурации проекта (BUSINESS, BANK) (CT-P0-07)"""
    __tablename__ = "project_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))  # BUSINESS_DEFAULT, BANK_DEFAULT
    project_type: Mapped[str] = mapped_column(String(20))  # BUSINESS, BANK
    required_modules: Mapped[str] = mapped_column(Text)  # JSON/text list
    config_defaults: Mapped[str] = mapped_column(Text)  # JSON dict
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BotInstance(Base):
    """Конкретный экземпляр бота (инстанс) (CT-P0-07)"""
    __tablename__ = "bot_instances"

    instance_id: Mapped[str] = mapped_column(String(100), primary_key=True)  # unique instance key
    token: Mapped[str] = mapped_column(String(255))
    region_code: Mapped[str] = mapped_column(String(10), ForeignKey("regions.code"))
    project_type: Mapped[str] = mapped_column(String(20))  # BUSINESS, BANK
    status: Mapped[str] = mapped_column(String(30), default="ready")  # ready, active, suspended, archived
    support_group_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProvisioningEvent(Base):
    """События жизненного цикла инстансов (readiness, activation, suspend, rollback) (CT-P0-07)"""
    __tablename__ = "provisioning_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(100), ForeignKey("bot_instances.instance_id"))
    event_type: Mapped[str] = mapped_column(String(50))  # create, activate, suspend, rollback
    actor_id: Mapped[int] = mapped_column(BigInteger)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
