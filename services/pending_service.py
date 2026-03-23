import asyncio
import html
import logging
import re
from typing import Dict, List, Sequence

from aiogram import Bot

from config import settings
from database.database import get_session
from database.repository import (
    ChatRepository,
    PendingRequestRepository,
    TrainingRepository,
    UserRepository,
)
from locales.loader import get_text
from services.ai_service import AIService
from services.bot_profile_service import get_bot_key_for_bot, get_user_bot_key
from services.thread_service import ThreadService

logger = logging.getLogger(__name__)


def markdown_to_html(text: str) -> str:
    text = html.escape(text or "")
    text = re.sub(r"\*\*([^\*]+?)\*\*", r"<b>\1</b>", text, flags=re.UNICODE)
    text = re.sub(r"\*([^\*]+?)\*", r"<i>\1</i>", text, flags=re.UNICODE)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text, flags=re.UNICODE)
    text = re.sub(r"\[([^\]]+?)\]\(([^\)]+?)\)", r"<a href=\"\2\">\1</a>", text, flags=re.UNICODE)
    return text


def _trim_history(messages: List[Dict[str, str]], keep_recent: int = 20) -> List[Dict[str, str]]:
    if len(messages) <= keep_recent:
        return messages

    old_part = messages[:-keep_recent]
    recent_part = messages[-keep_recent:]
    user_questions = [item["content"] for item in old_part if item["role"] == "user"]

    summary = "Earlier context summary: "
    if user_questions:
        summary += "; ".join(q[:80] for q in user_questions[:5])
    else:
        summary += "general support dialogue"

    return [{"role": "system", "content": summary}] + recent_part


class PendingService:
    _concurrency_limit = 4

    @staticmethod
    async def process_pending_requests(bots: Sequence[Bot] | Bot):
        logger.info("Starting pending queue processing")

        if isinstance(bots, Bot):
            bot_list: List[Bot] = [bots]
        else:
            bot_list = list(bots)

        if not bot_list:
            logger.warning("No bots provided to pending processor")
            return

        async with get_session() as session:
            pending_repo = PendingRequestRepository(session)
            pending_requests = await pending_repo.get_all_pending()

        if not pending_requests:
            logger.info("No pending requests found")
            return

        logger.info("Pending requests to process: %s", len(pending_requests))

        semaphore = asyncio.Semaphore(PendingService._concurrency_limit)

        async def pick_bot(user_id: int) -> Bot:
            wanted_key = await get_user_bot_key(user_id)
            if wanted_key:
                for item in bot_list:
                    if get_bot_key_for_bot(item) == wanted_key:
                        return item
            return bot_list[0]

        async def worker(request_item):
            async with semaphore:
                bot = await pick_bot(request_item.user_id)
                await PendingService._process_single_request(bot, request_item)

        await asyncio.gather(*(worker(item) for item in pending_requests), return_exceptions=True)

    @staticmethod
    async def _process_single_request(bot: Bot, request):
        async with get_session() as session:
            pending_repo = PendingRequestRepository(session)
            await pending_repo.mark_started(request.id)

        try:
            ai_service = await AIService.get_service()
            if not ai_service:
                raise RuntimeError("AI service unavailable")

            async with get_session() as session:
                user_repo = UserRepository(session)
                chat_repo = ChatRepository(session)
                training_repo = TrainingRepository(session)

                user = await user_repo.get_by_id(request.user_id)
                if not user:
                    raise RuntimeError(f"User {request.user_id} not found")

                language = user.language
                thread_id = user.thread_id

                active_session = await chat_repo.get_active_session(request.user_id)
                if not active_session:
                    raise RuntimeError(f"No active session for user {request.user_id}")

                history = await chat_repo.get_session_history(active_session.id, limit=40)
                messages = [
                    {"role": item.role, "content": item.content}
                    for item in history
                    if item.role in {"user", "assistant"}
                ]
                messages = _trim_history(messages)

                system_prompt = await ai_service.get_system_prompt(training_repo, language)

            response_parts: List[str] = []
            async for chunk in ai_service.get_response_stream(
                messages=messages,
                system_prompt=system_prompt,
                user_id=request.user_id,
                thread_id=thread_id,
                bot=bot,
            ):
                response_parts.append(chunk)

            response_text = "".join(response_parts).strip()
            if not response_text:
                raise RuntimeError("Empty AI response")

            lowered = response_text.lower()
            if "ignore_offtopic" in lowered:
                off_topic_text = get_text("off_topic", language)
                if settings.SUPPORT_GROUP_ID:
                    thread_service = ThreadService(bot)
                    await thread_service.send_system_message(
                        user_id=request.user_id,
                        text="AI пометил вопрос как оффтоп. Сообщение пользователя передано в поддержку.",
                        username=user.username,
                        first_name=user.first_name,
                    )
                    await thread_service.send_user_message(
                        user_id=request.user_id,
                        text=request.message_text,
                        username=user.username,
                        first_name=user.first_name,
                    )
                    await thread_service.send_ai_message(
                        user_id=request.user_id,
                        text=off_topic_text,
                        username=user.username,
                        first_name=user.first_name,
                    )
                await bot.send_message(
                    chat_id=request.user_id,
                    text=off_topic_text,
                )
                async with get_session() as session:
                    pending_repo = PendingRequestRepository(session)
                    await pending_repo.mark_completed(request.id)
                return

            clean_text = (
                response_text
                .replace("ignore_offtopic", "")
                .replace("IGNORE_OFFTOPIC", "")
                .replace("call_people", "")
                .replace("CALL_PEOPLE", "")
                .strip()
            )

            if not clean_text:
                raise RuntimeError("AI response became empty after cleaning")

            if "call_people" in lowered:
                async with get_session() as session:
                    chat_repo = ChatRepository(session)
                    await chat_repo.deactivate_ai(request.user_id)
                    await chat_repo.add_message(request.user_id, "assistant", clean_text)

                await bot.send_message(request.user_id, markdown_to_html(clean_text), parse_mode="HTML")
                await bot.send_message(request.user_id, get_text("human_called", language), parse_mode="HTML")

                if settings.SUPPORT_GROUP_ID:
                    thread_service = ThreadService(bot)
                    await thread_service.notify_human_needed(
                        user_id=request.user_id,
                        username=user.username,
                        first_name=user.first_name,
                    )
                    await thread_service.send_user_message(
                        user_id=request.user_id,
                        text=request.message_text,
                        username=user.username,
                        first_name=user.first_name,
                    )
                    await thread_service.send_ai_message(
                        user_id=request.user_id,
                        text=clean_text,
                        username=user.username,
                        first_name=user.first_name,
                    )
            else:
                response_message = await bot.send_message(
                    chat_id=request.user_id,
                    text=markdown_to_html(clean_text),
                    parse_mode="HTML",
                )

                async with get_session() as session:
                    chat_repo = ChatRepository(session)
                    await chat_repo.add_message(
                        user_id=request.user_id,
                        role="assistant",
                        content=clean_text,
                        message_id=response_message.message_id,
                    )

                if settings.SUPPORT_GROUP_ID:
                    thread_service = ThreadService(bot)
                    await thread_service.send_user_message(
                        user_id=request.user_id,
                        text=request.message_text,
                        username=user.username,
                        first_name=user.first_name,
                    )
                    await thread_service.send_ai_message(
                        user_id=request.user_id,
                        text=clean_text,
                        username=user.username,
                        first_name=user.first_name,
                    )

            async with get_session() as session:
                pending_repo = PendingRequestRepository(session)
                await pending_repo.mark_completed(request.id)

            logger.info("Pending request %s completed", request.id)

        except Exception as error:
            logger.error("Pending request %s failed: %s", request.id, error)
            try:
                thread_service = ThreadService(bot)
                await thread_service.send_log_message(
                    f"Pending request failed. request_id={request.id} user_id={request.user_id} error={error}"
                )
            except Exception:
                pass

            try:
                language = "en"
                async with get_session() as session:
                    user_repo = UserRepository(session)
                    user = await user_repo.get_by_id(request.user_id)
                    if user:
                        language = user.language
                await bot.send_message(request.user_id, get_text("error_try_later", language))
            except Exception:
                pass

            async with get_session() as session:
                pending_repo = PendingRequestRepository(session)
                await pending_repo.mark_failed(request.id)
