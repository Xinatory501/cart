import html
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from config import settings
from database.database import get_session
from database.models import User
from database.repository import ConfigRepository, UserRepository
from services.bot_profile_service import get_profile_for_bot, get_user_bot_key, set_user_bot_key

logger = logging.getLogger(__name__)


class ThreadService:
    _TOPIC_MISSING_MARKERS = (
        "thread not found",
        "topic closed",
        "topic not found",
        "message thread not found",
    )

    _FORUM_DISABLED_MARKERS = (
        "chat_forum_disabled",
        "forum is disabled",
        "forum_disabled",
    )

    _PERMISSION_MARKERS = (
        "not enough rights",
        "need administrator rights",
        "chat_admin_required",
        "not enough rights to manage topics",
    )

    _READY_TTL = timedelta(seconds=60)
    _NOTIFY_TTL = timedelta(minutes=5)
    _READY_CACHE: dict[str, tuple[bool, datetime]] = {}
    _NOTIFY_CACHE: dict[str, datetime] = {}

    def __init__(self, bot: Bot):
        self.bot = bot
        self.profile = get_profile_for_bot(bot)

    @property
    def support_group_id(self) -> Optional[int]:
        return settings.SUPPORT_GROUP_ID

    def _is_support_group_configured(self) -> bool:
        return bool(self.support_group_id)

    def _cache_key(self) -> str:
        return f"{self.profile.key}:{self.support_group_id}"

    def _should_notify(self, key: str) -> bool:
        last = self._NOTIFY_CACHE.get(key)
        now = datetime.utcnow()
        if not last or now - last >= self._NOTIFY_TTL:
            self._NOTIFY_CACHE[key] = now
            return True
        return False

    def _user_thread_key(self, user_id: int) -> str:
        return f"support_thread:{self.profile.key}:{user_id}"

    def _log_thread_key(self) -> str:
        return f"support_log_thread:{self.profile.key}"

    @staticmethod
    def _thread_owner_key(thread_id: int) -> str:
        return f"support_thread_owner:{thread_id}"

    @staticmethod
    def _thread_user_key(thread_id: int) -> str:
        return f"support_thread_user:{thread_id}"

    @staticmethod
    def _to_int(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _format_user_display(user_id: int, username: Optional[str], first_name: Optional[str]) -> str:
        if username:
            return f"@{username}"
        if first_name:
            return first_name
        return f"User {user_id}"

    def _format_topic_name(self, user_id: int, username: Optional[str], first_name: Optional[str]) -> str:
        display = self._format_user_display(user_id, username, first_name)
        name = f"{self.profile.topic_flag} {display}".replace("\n", " ").strip()
        if len(name) > 120:
            name = name[:117].rstrip() + "..."
        return name


    @staticmethod
    def _escape(text: str) -> str:
        return html.escape(text or "")

    @classmethod
    def _is_topic_missing_error(cls, error: Exception) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in cls._TOPIC_MISSING_MARKERS)

    @classmethod
    def _is_forum_disabled_error(cls, error: Exception) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in cls._FORUM_DISABLED_MARKERS)

    @classmethod
    def _is_permission_error(cls, error: Exception) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in cls._PERMISSION_MARKERS)

    async def _ensure_support_group_ready(self, require_manage_topics: bool = False) -> bool:
        if not self._is_support_group_configured():
            return False

        cache_key = self._cache_key()
        cached = self._READY_CACHE.get(cache_key)
        now = datetime.utcnow()
        if cached and now - cached[1] < self._READY_TTL:
            return cached[0]

        ready = True
        reason = None
        error: Optional[Exception] = None

        try:
            chat = await self.bot.get_chat(self.support_group_id)
        except Exception as exc:
            ready = False
            error = exc
            reason = "Не удалось получить группу поддержки. Проверьте ID и добавьте бота в группу."
        else:
            if not getattr(chat, "is_forum", False):
                ready = False
                reason = "В группе поддержки выключены темы (форум). Включите темы в настройках группы."

        if ready and require_manage_topics:
            try:
                member = await self.bot.get_chat_member(self.support_group_id, self.bot.id)
                status = getattr(member, "status", "")
                can_manage_topics = getattr(member, "can_manage_topics", False)
                if status != "creator" and not can_manage_topics:
                    ready = False
                    reason = "Бот не имеет права «Управление темами» в группе поддержки."
            except Exception as exc:
                ready = False
                error = exc
                if not reason:
                    reason = "Не удалось проверить права бота в группе поддержки."

        self._READY_CACHE[cache_key] = (ready, now)

        if not ready and self._should_notify(cache_key):
            await self._notify_admins_about_permissions(error=error, reason=reason)

        return ready


    async def _user_belongs_to_current_bot(self, user_id: int, allow_unassigned: bool = True) -> bool:
        active_bot = await get_user_bot_key(user_id)
        if not active_bot:
            return allow_unassigned
        return active_bot == self.profile.key

    async def get_thread_id_for_user(self, user_id: int) -> Optional[int]:
        if not self._is_support_group_configured():
            return None

        async with get_session() as session:
            config_repo = ConfigRepository(session)
            user_repo = UserRepository(session)

            mapped_value = await config_repo.get(self._user_thread_key(user_id))
            mapped_id = self._to_int(mapped_value)
            if mapped_id:
                owner = await config_repo.get(self._thread_owner_key(mapped_id))
                if not owner or owner == self.profile.key:
                    if not owner:
                        await config_repo.set(self._thread_owner_key(mapped_id), self.profile.key)
                    return mapped_id

            user = await user_repo.get_by_id(user_id)
            if user and user.thread_id:
                if not await self._user_belongs_to_current_bot(user_id):
                    return None

                owner = await config_repo.get(self._thread_owner_key(user.thread_id))
                if owner and owner != self.profile.key:
                    return None

                await config_repo.set(self._user_thread_key(user_id), str(user.thread_id))
                await config_repo.set(self._thread_owner_key(user.thread_id), self.profile.key)
                await config_repo.set(self._thread_user_key(user.thread_id), str(user_id))
                return user.thread_id

        return None

    async def is_thread_owned_by_current_bot(self, thread_id: int) -> bool:
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            user_repo = UserRepository(session)

            owner = await config_repo.get(self._thread_owner_key(thread_id))
            if owner:
                return owner == self.profile.key

            user_id_value = await config_repo.get(self._thread_user_key(thread_id))
            user_id = self._to_int(user_id_value)
            if user_id:
                if not await self._user_belongs_to_current_bot(user_id, allow_unassigned=False):
                    return False

                await config_repo.set(self._thread_owner_key(thread_id), self.profile.key)
                await config_repo.set(self._user_thread_key(user_id), str(thread_id))
                return True

            result = await session.execute(select(User).where(User.thread_id == thread_id))
            user = result.scalar_one_or_none()
            if not user:
                return False

            if not await self._user_belongs_to_current_bot(user.id, allow_unassigned=False):
                return False

            await config_repo.set(self._thread_owner_key(thread_id), self.profile.key)
            await config_repo.set(self._thread_user_key(thread_id), str(user.id))
            await config_repo.set(self._user_thread_key(user.id), str(thread_id))
            return True

    async def backfill_thread_ownership(self) -> int:
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            result = await session.execute(select(User).where(User.thread_id != None))
            users = list(result.scalars().all())

            updated = 0
            for user in users:
                if not user.thread_id:
                    continue

                active_bot = await config_repo.get(f"user_active_bot:{user.id}")
                if active_bot != self.profile.key:
                    continue

                owner_key = self._thread_owner_key(user.thread_id)
                if await config_repo.get(owner_key):
                    continue

                await config_repo.set(owner_key, self.profile.key)
                await config_repo.set(self._thread_user_key(user.thread_id), str(user.id))
                await config_repo.set(self._user_thread_key(user.id), str(user.thread_id))
                updated += 1

            return updated

    async def get_user_id_by_thread(self, thread_id: int) -> Optional[int]:
        if not await self.is_thread_owned_by_current_bot(thread_id):
            return None

        async with get_session() as session:
            config_repo = ConfigRepository(session)

            user_id_value = await config_repo.get(self._thread_user_key(thread_id))
            user_id = self._to_int(user_id_value)
            if user_id:
                return user_id

            result = await session.execute(select(User).where(User.thread_id == thread_id))
            user = result.scalar_one_or_none()
            if not user:
                return None

            await config_repo.set(self._thread_user_key(thread_id), str(user.id))
            await config_repo.set(self._user_thread_key(user.id), str(thread_id))
            await config_repo.set(self._thread_owner_key(thread_id), self.profile.key)
            return user.id

    async def _save_thread_mapping(self, user_id: int, thread_id: int) -> None:
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            user_repo = UserRepository(session)

            await config_repo.set(self._user_thread_key(user_id), str(thread_id))
            await config_repo.set(self._thread_owner_key(thread_id), self.profile.key)
            await config_repo.set(self._thread_user_key(thread_id), str(user_id))
            await user_repo.update_thread_id(user_id, thread_id)

        await set_user_bot_key(user_id, self.profile.key)

    async def _clear_thread_mapping(self, user_id: int, thread_id: Optional[int]) -> None:
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            user_repo = UserRepository(session)

            await config_repo.delete(self._user_thread_key(user_id))
            if thread_id:
                await config_repo.delete(self._thread_owner_key(thread_id))
                await config_repo.delete(self._thread_user_key(thread_id))

            user = await user_repo.get_by_id(user_id)
            if user and user.thread_id == thread_id:
             await user_repo.update_thread_id(user_id, None)

    async def ensure_log_thread(self) -> Optional[int]:
        if not self._is_support_group_configured():
            return None

        if not await self._ensure_support_group_ready(require_manage_topics=True):
            return None

        async with get_session() as session:
            config_repo = ConfigRepository(session)
            mapped_value = await config_repo.get(self._log_thread_key())
            mapped_id = self._to_int(mapped_value)
            if mapped_id:
                return mapped_id

        try:
            forum_topic = await self.bot.create_forum_topic(
                chat_id=self.support_group_id,
                name="Логи",
            )
        except TelegramAPIError as error:
            logger.error("Failed to create log thread: %s", error)
            return None

        thread_id = forum_topic.message_thread_id
        async with get_session() as session:
            config_repo = ConfigRepository(session)
            await config_repo.set(self._log_thread_key(), str(thread_id))

        return thread_id

    async def send_log_message(self, text: str) -> bool:
        if not self._is_support_group_configured():
            logger.error("Support group is not configured. Log: %s", text)
            return False

        thread_id = await self.ensure_log_thread()
        if not thread_id:
            logger.error("Log thread is missing. Log: %s", text)
            return False

        safe_text = self._escape(text)

        try:
            await self.bot.send_message(
                chat_id=self.support_group_id,
                message_thread_id=thread_id,
                text=safe_text,
                parse_mode="HTML",
            )
            return True
        except TelegramAPIError as error:
            logger.warning("Failed to send log message: %s", error)
            if self._is_topic_missing_error(error):
                async with get_session() as session:
                    config_repo = ConfigRepository(session)
                    await config_repo.delete(self._log_thread_key())
                new_thread_id = await self.ensure_log_thread()
                if new_thread_id:
                    try:
                        await self.bot.send_message(
                            chat_id=self.support_group_id,
                            message_thread_id=new_thread_id,
                            text=safe_text,
                            parse_mode="HTML",
                        )
                        return True
                    except TelegramAPIError as retry_error:
                        logger.error("Failed to resend log message: %s", retry_error)
            return False

    async def create_thread_for_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> Optional[int]:
        if not self._is_support_group_configured():
            logger.warning("SUPPORT_GROUP_ID is not configured; skipping thread creation")
            return None

        if not await self._ensure_support_group_ready(require_manage_topics=True):
            return None

        try:
            if not username or not first_name:
                async with get_session() as session:
                    user_repo = UserRepository(session)
                    user = await user_repo.get_by_id(user_id)
                    if user:
                        username = username or user.username
                        first_name = first_name or user.first_name

            thread_name = self._format_topic_name(user_id, username, first_name)

            forum_topic = await self.bot.create_forum_topic(
                chat_id=self.support_group_id,
                name=thread_name,
            )

            thread_id = forum_topic.message_thread_id
            await self._save_thread_mapping(user_id, thread_id)

            info_message = (
                "<b>Новый пользователь</b>\n\n"
                f"Бот: <code>{self.profile.key}</code>\n"
                f"User ID: <code>{user_id}</code>\n"
                f"Username: {f'@{username}' if username else 'Не указан'}\n"
                f"Имя: {first_name or 'Не указано'}\n\n"
                "AI активен.\n"
                "Сообщение участника в теме отключит AI и уйдет пользователю.\n"
                "Чтобы включить AI: /ai"
            )

            await self.bot.send_message(
                chat_id=self.support_group_id,
                message_thread_id=thread_id,
                text=info_message,
                parse_mode="HTML",
            )

            logger.info(
                "Created thread %s for user %s (%s)",
                thread_id,
                user_id,
                self.profile.key,
            )
            return thread_id

        except TelegramAPIError as error:
            logger.error("Failed to create thread for user %s: %s", user_id, error)
            if self._is_permission_error(error) or self._is_forum_disabled_error(error):
                await self._notify_admins_about_permissions(error=error)
            return None

    async def ensure_thread_for_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> Optional[int]:
        existing_thread_id = await self.get_thread_id_for_user(user_id)
        if existing_thread_id and await self.is_thread_owned_by_current_bot(existing_thread_id):
            await set_user_bot_key(user_id, self.profile.key)
            return existing_thread_id

        if not await self._ensure_support_group_ready(require_manage_topics=True):
            return None

        return await self.create_thread_for_user(
            user_id=user_id,
            username=username,
            first_name=first_name,
        )

    def _build_user_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton(
                    text="Заблокировать пользователя",
                    callback_data=f"ban_user_{user_id}",
                )
            ]
        ]

        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _send_message(
        self,
        user_id: int,
        text: str,
        prefix: Optional[str] = None,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        from_user: bool = False,
        _retry: bool = False,
    ) -> bool:
        if not self._is_support_group_configured():
            logger.warning("SUPPORT_GROUP_ID is not configured; skipping support message")
            return False

        thread_id = await self.ensure_thread_for_user(
            user_id=user_id,
            username=username,
            first_name=first_name,
        )

        if not thread_id:
            logger.warning("Thread ID is missing for user %s", user_id)
            return False

        if not await self.is_thread_owned_by_current_bot(thread_id):
            return False

        safe_text = self._escape(text)
        full_text = f"{prefix}{safe_text}" if prefix else safe_text

        keyboard = None
        if from_user:
            keyboard = self._build_user_keyboard(user_id)

        try:
            await self.bot.send_message(
                chat_id=self.support_group_id,
                message_thread_id=thread_id,
                text=full_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return True

        except TelegramAPIError as error:
            logger.warning("Failed to send to thread %s: %s", thread_id, error)
            if self._is_permission_error(error) or self._is_forum_disabled_error(error):
                await self._notify_admins_about_permissions(error=error)
                return False

            if not _retry and self._is_topic_missing_error(error):
                await self._clear_thread_mapping(user_id, thread_id)
                new_thread_id = await self.ensure_thread_for_user(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                )
                if new_thread_id:
                    return await self._send_message(
                        user_id=user_id,
                        text=text,
                        prefix=prefix,
                        username=username,
                        first_name=first_name,
                        from_user=from_user,
                        _retry=True,
                    )
            return False

    async def send_user_message(
        self,
        user_id: int,
        text: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> bool:
        return await self._send_message(
            user_id=user_id,
            text=text,
            prefix="<b>Пользователь:</b>\n",
            username=username,
            first_name=first_name,
            from_user=True,
        )

    async def send_ai_message(
        self,
        user_id: int,
        text: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> bool:
        return await self._send_message(
            user_id=user_id,
            text=text,
            prefix="<b>AI ответ:</b>\n",
            username=username,
            first_name=first_name,
            from_user=False,
        )

    async def send_system_message(
        self,
        user_id: int,
        text: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> bool:
        return await self._send_message(
            user_id=user_id,
            text=text,
            prefix="<b>Система:</b>\n",
            username=username,
            first_name=first_name,
            from_user=False,
        )

    async def notify_human_needed(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> bool:
        return await self._send_message(
            user_id=user_id,
            text=(
                "Требуется поддержка.\n"
                "Пользователь запросил человека.\n"
                "AI ответы приостановлены."
            ),
            prefix="<b>Внимание:</b>\n",
            username=username,
            first_name=first_name,
            from_user=False,
        )

    async def _notify_admins_about_permissions(
        self,
        error: Optional[Exception] = None,
        reason: Optional[str] = None,
    ) -> None:
        base_lines = [
            "Бот не может создать тему или написать в тему поддержки.",
            "Проверьте: группа = форум, бот админ, право «Управление темами».",
        ]
        if reason:
            base_lines.append(f"Причина: {reason}")
        if error:
            base_lines.append(f"Ошибка: {str(error)[:200]}")
        message = "\n".join(base_lines)

        logger.error(message)







