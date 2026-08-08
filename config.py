"""
Конфигурация экземпляра бота (Instance Profile).
Загружается из переменных окружения при старте.
Поддерживает мультибот-архитектуру через отдельные .env на деплой.
"""
from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional


class Settings(BaseSettings):
    # ---- Идентификация экземпляра ----
    INSTANCE_ID: str = "cartame_by"
    CLIENT_CODE: str = "CARTAME"
    PROJECT_CODE: str = "CARTAME_SUPPORT_BY"
    REGION_CODE: str = "BY"
    PROJECT_TYPE: str = "BUSINESS"  # BUSINESS | BANK

    # ---- Telegram ----
    # Новый формат (один токен на экземпляр)
    BOT_TOKEN: str = ""
    # Обратная совместимость со старым форматом BOT1-BOT6
    BOT1_TOKEN: str = ""
    BOT2_TOKEN: str = ""
    BOT3_TOKEN: str = ""
    BOT4_TOKEN: str = ""
    BOT5_TOKEN: str = ""
    BOT6_TOKEN: str = ""
    BOT1_TOKE: str = ""
    BOT2_TOKE: str = ""
    BOT3_TOKE: str = ""
    BOT4_TOKE: str = ""
    BOT5_TOKE: str = ""
    BOT6_TOKE: str = ""
    SUPPORT_GROUP_ID: Optional[int] = None
    ADMIN_IDS: str = ""

    # ---- База данных ----
    DATABASE_URL: str = Field(default='sqlite+aiosqlite:///./data/bot.db')

    # ---- Безопасность и логирование ----
    SECRET_ENCRYPTION_KEY: str = ""
    LOG_FORMAT: str = "text"
    LOG_LEVEL: str = "INFO"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000"

    # ---- Локализация ----
    DEFAULT_LANGUAGE: str = "ru"
    INSTANCE_LANGUAGES: str = "ru"  # Разделённые запятой языки экземпляра
    INSTANCE_TIMEZONE: str = "Europe/Minsk"

    @property
    def admin_ids(self) -> List[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(id.strip()) for id in self.ADMIN_IDS.split(',') if id.strip()]

    @property
    def instance_languages(self) -> List[str]:
        """Список языков, доступных в данном экземпляре."""
        raw = self.INSTANCE_LANGUAGES or 'ru'
        langs = [l.strip() for l in raw.split(',') if l.strip()]
        # REG-05: map kz->kk
        return ['kk' if l == 'kz' else l for l in langs]

    @property
    def primary_bot_token(self) -> str:
        """Возвращает токен бота: сначала BOT_TOKEN, потом BOT1_TOKEN (обратная совместимость)."""
        return (
            self.BOT_TOKEN
            or self.BOT1_TOKEN
            or self.BOT1_TOKE
            or ""
        ).strip()

    # --- Обратная совместимость для мультибот-режима ---
    @property
    def bot1_token(self) -> str:
        return (self.BOT1_TOKEN or self.BOT1_TOKE or "").strip()

    @property
    def bot2_token(self) -> str:
        return (self.BOT2_TOKEN or self.BOT2_TOKE or "").strip()

    @property
    def bot3_token(self) -> str:
        return (self.BOT3_TOKEN or self.BOT3_TOKE or "").strip()

    @property
    def bot4_token(self) -> str:
        return (self.BOT4_TOKEN or self.BOT4_TOKE or "").strip()

    @property
    def bot5_token(self) -> str:
        return (self.BOT5_TOKEN or self.BOT5_TOKE or "").strip()

    @property
    def bot6_token(self) -> str:
        return (self.BOT6_TOKEN or self.BOT6_TOKE or "").strip()

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
