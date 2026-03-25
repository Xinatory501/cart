from dataclasses import dataclass
from typing import Dict, List, Optional

from aiogram import Bot

from config import settings
from database.database import get_session
from database.repository import ConfigRepository


@dataclass(frozen=True)
class BotProfile:
    key: str
    region: str
    default_language: str
    topic_flag: str


_RUNTIME_PROFILES: Dict[int, BotProfile] = {}


_PROFILE_DEFINITIONS = [
    (
        "BOT1",
        "belarus",
        "ru",
        "🇧🇾",
        lambda: settings.bot1_token,
    ),
    (
        "BOT2",
        "kazakhstan",
        "kz",
        "🇰🇿",
        lambda: settings.bot2_token,
    ),
    (
        "BOT3",
        "uzbekistan",
        "uz",
        "🇺🇿",
        lambda: settings.bot3_token,
    ),
    (
        "BOT4",
        "custom_4",
        "en",
        "BOT4",
        lambda: settings.bot4_token,
    ),
    (
        "BOT5",
        "custom_5",
        "en",
        "BOT5",
        lambda: settings.bot5_token,
    ),
    (
        "BOT6",
        "custom_6",
        "en",
        "BOT6",
        lambda: settings.bot6_token,
    ),
]


def get_launch_profiles() -> List[tuple[str, BotProfile]]:
    profiles: List[tuple[str, BotProfile]] = []

    for key, region, default_language, topic_flag, token_getter in _PROFILE_DEFINITIONS:
        token = token_getter()
        if not token:
            continue

        profiles.append(
            (
                token,
                BotProfile(
                    key=key,
                    region=region,
                    default_language=default_language,
                    topic_flag=topic_flag,
                ),
            )
        )

    return profiles


def register_runtime_profile(bot_id: int, profile: BotProfile) -> None:
    _RUNTIME_PROFILES[bot_id] = profile


def get_profile_for_bot_id(bot_id: int) -> BotProfile:
    return _RUNTIME_PROFILES.get(
        bot_id,
        BotProfile(
            key="BOT1",
            region="belarus",
            default_language="ru",
            topic_flag="🇧🇾",
        ),
    )


def get_profile_for_bot(bot: Bot) -> BotProfile:
    return get_profile_for_bot_id(bot.id)


def get_default_language_for_bot(bot: Bot) -> str:
    return get_profile_for_bot(bot).default_language


def get_bot_key_for_bot(bot: Bot) -> str:
    return get_profile_for_bot(bot).key


def get_bot_key_for_bot_id(bot_id: int) -> str:
    return get_profile_for_bot_id(bot_id).key


async def set_user_bot_key(user_id: int, bot_key: str) -> None:
    key = f"user_active_bot:{user_id}"
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.set(key, bot_key, "Stores which bot instance serves this user")


async def get_user_bot_key(user_id: int) -> Optional[str]:
    key = f"user_active_bot:{user_id}"
    async with get_session() as session:
        config_repo = ConfigRepository(session)
        value = await config_repo.get(key)
        return value or None
