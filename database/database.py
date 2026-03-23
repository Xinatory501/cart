import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from database.models import Base

logger = logging.getLogger(__name__)

engine: AsyncEngine = None
async_session_maker: async_sessionmaker[AsyncSession] = None

def get_engine() -> AsyncEngine:
    global engine
    if engine is None:
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
        )
    return engine

def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global async_session_maker
    if async_session_maker is None:
        async_session_maker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return async_session_maker

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()

async def init_db() -> None:
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized successfully")

    await init_default_config()

async def init_default_config() -> None:
    from database.repository import ConfigRepository, AIProviderRepository, APIKeyRepository, AIModelRepository, UserRepository

    async with get_session() as session:
        config_repo = ConfigRepository(session)
        ai_provider_repo = AIProviderRepository(session)
        api_key_repo = APIKeyRepository(session)
        model_repo = AIModelRepository(session)
        user_repo = UserRepository(session)

        existing_privacy = await config_repo.get("privacy_policy_url")
        if not existing_privacy:
            await config_repo.set(
                "privacy_policy_url",
                "https://cartame.com/privacy",
                "URL политики конфиденциальности"
            )
            logger.info("Default privacy policy URL set")

        if not await config_repo.get("antiflood_threshold"):
            await config_repo.set("antiflood_threshold", "1", "Порог антифлуда (максимум сообщений)")
        if not await config_repo.get("antiflood_time_window"):
            await config_repo.set("antiflood_time_window", "3", "Временное окно антифлуда (сек)")
        if not await config_repo.get("autoban_duration"):
            await config_repo.set("autoban_duration", "900", "Длительность автобана (сек)")

        all_providers = await ai_provider_repo.get_all()
        if not all_providers:
            openrouter = await ai_provider_repo.create(
                name="openrouter",
                display_name="OpenRouter",
                base_url="https://openrouter.ai/api/v1",
                is_default=True
            )
            await api_key_repo.create(
                provider_id=openrouter.id,
                api_key="your_openrouter_api_key_here",
                name="Ключ 1"
            )
            await model_repo.create(openrouter.id, "deepseek/deepseek-r1-0528:free", "DeepSeek R1 Free", is_default=True)
            await model_repo.create(openrouter.id, "openai/gpt-3.5-turbo", "GPT-3.5 Turbo", is_default=False)
            logger.info("OpenRouter provider created")

            groq = await ai_provider_repo.create(
                name="groq",
                display_name="Groq",
                base_url="https://api.groq.com/openai/v1",
                is_default=False
            )
            await api_key_repo.create(
                provider_id=groq.id,
                api_key="your_groq_api_key_here",
                name="Ключ 1"
            )
            await model_repo.create(groq.id, "llama-3.1-8b-instant", "Llama 3.1 8B", is_default=True)
            await model_repo.create(groq.id, "mixtral-8x7b-32768", "Mixtral 8x7B", is_default=False)
            logger.info("Groq provider created")

            openai = await ai_provider_repo.create(
                name="openai",
                display_name="OpenAI",
                base_url=None,
                is_default=False
            )
            await api_key_repo.create(
                provider_id=openai.id,
                api_key="your_openai_api_key_here",
                name="Ключ 1"
            )
            await model_repo.create(openai.id, "gpt-3.5-turbo", "GPT-3.5 Turbo", is_default=True)
            await model_repo.create(openai.id, "gpt-4", "GPT-4", is_default=False)
            logger.info("OpenAI provider created")

            logger.info("Default AI providers created with models and placeholder API keys")

        normalized_keys = await api_key_repo.normalize_existing_keys()
        if normalized_keys:
            logger.info(f"Normalized {normalized_keys} API key(s).")

        disabled_placeholders = await api_key_repo.deactivate_placeholder_keys()
        if disabled_placeholders:
            logger.warning(
                f"Disabled {disabled_placeholders} placeholder API key(s). Add real keys in admin panel."
            )

        for admin_id in settings.admin_ids:
            existing_user = await user_repo.get_by_id(admin_id)
            if not existing_user:
                await user_repo.create(
                    user_id=admin_id,
                    username=None,
                    first_name="Admin",
                    last_name=None
                )
                await user_repo.set_role(admin_id, "admin")
                logger.info(f"Created initial admin user: {admin_id}")
            elif existing_user.role != "admin":
                await user_repo.set_role(admin_id, "admin")
                logger.info(f"Set admin role for existing user: {admin_id}")

async def close_db() -> None:
    global engine, async_session_maker

    if engine is not None:
        await engine.dispose()
        engine = None

    async_session_maker = None
    logger.info("Database connection closed")
