import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple

from openai import APIError, AsyncOpenAI, RateLimitError

from database.database import get_session
from database.models import AIModel, AIProvider, APIKey
from database.repository import (
    AIModelRepository,
    AIProviderRepository,
    APIKeyRepository,
    TrainingRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Candidate:
    provider: AIProvider
    api_key: APIKey
    model: AIModel


class AIService:
    _request_semaphore = asyncio.Semaphore(12)

    _AUTH_MARKERS = (
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "invalid_api_key",
        "invalid api key",
        "incorrect api key",
        "missing authentication",
        "missing authentication header",
        "access denied",
        "authenticationerror",
    )

    _RATE_LIMIT_MARKERS = (
        "429",
        "rate limit",
        "too many requests",
        "quota",
    )

    _MODEL_MARKERS = (
        "model_not_found",
        "invalid_model",
        "model does not exist",
        "not found",
        "does not exist",
        "not a valid model id",
        "unknown model",
        "unsupported model",
        "not a valid model",
        "no endpoints found",
    )

    _LOCAL_HOST_MARKERS = (
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "host.docker.internal",
    )

    def __init__(self, provider: AIProvider, api_key: APIKey, model: AIModel):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.client = self._create_client()

    @staticmethod
    def _is_local_provider(provider: AIProvider) -> bool:
        provider_name = (provider.name or "").lower()
        base_url = (provider.base_url or "").lower()

        if provider_name in {"ollama", "lmstudio", "local"}:
            return True

        if any(marker in base_url for marker in AIService._LOCAL_HOST_MARKERS):
            return True

        return False

    @staticmethod
    def _is_auth_error(error_message: str) -> bool:
        text = (error_message or "").lower()
        return any(marker in text for marker in AIService._AUTH_MARKERS)

    @staticmethod
    def _is_model_error(error_message: str) -> bool:
        text = (error_message or "").lower()
        return any(marker in text for marker in AIService._MODEL_MARKERS)

    @staticmethod
    def _is_rate_limit_error(error_message: str) -> bool:
        text = (error_message or "").lower()
        return any(marker in text for marker in AIService._RATE_LIMIT_MARKERS)

    @staticmethod
    def _safe_key_name(api_key: APIKey) -> str:
        return api_key.name or f"key#{api_key.id}"

    def _effective_api_key(self) -> str:
        key = APIKeyRepository.normalize_api_key(self.api_key.api_key)
        if key:
            return key
        if self._is_local_provider(self.provider):
            return "local-no-auth"
        return ""

    def _resolve_base_url(self) -> Optional[str]:
        provider_name = (self.provider.name or "").lower()
        if provider_name == "openrouter":
            return self.provider.base_url or "https://openrouter.ai/api/v1"
        if provider_name == "groq":
            return self.provider.base_url or "https://api.groq.com/openai/v1"
        return self.provider.base_url

    def _create_client(self) -> AsyncOpenAI:
        api_key = self._effective_api_key()
        base_url = self._resolve_base_url()
        provider_name = (self.provider.name or "").lower()

        if provider_name == "openai" and not base_url:
            return AsyncOpenAI(api_key=api_key)

        headers: Dict[str, str] = {}
        if provider_name == "openrouter":
            headers["HTTP-Referer"] = "https://cartame.com"
            headers["X-Title"] = "CartaMe Support Bot"
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

        if provider_name == "groq" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return AsyncOpenAI(
            api_key=api_key or "local-no-auth",
            base_url=base_url,
            default_headers=headers or None,
        )

    @staticmethod
    async def _ordered_providers(
        ai_provider_repo: AIProviderRepository,
        provider_id: Optional[int] = None,
        exclude_provider_ids: Optional[Set[int]] = None,
    ) -> List[AIProvider]:
        excluded = set(exclude_provider_ids or set())
        all_active = await ai_provider_repo.get_all_active()
        by_id = {provider.id: provider for provider in all_active}

        ordered: List[AIProvider] = []
        seen: Set[int] = set()

        def push_if_ok(candidate: Optional[AIProvider]) -> None:
            if not candidate:
                return
            if candidate.id in seen or candidate.id in excluded:
                return
            if not candidate.is_active:
                return
            ordered.append(candidate)
            seen.add(candidate.id)

        if provider_id:
            push_if_ok(by_id.get(provider_id))
        else:
            push_if_ok(await ai_provider_repo.get_default())

        for provider in all_active:
            push_if_ok(provider)

        return ordered

    @staticmethod
    async def _available_keys_for_provider(
        api_key_repo: APIKeyRepository,
        provider: AIProvider,
    ) -> List[APIKey]:
        keys = await api_key_repo.get_by_provider(provider.id)
        if not keys:
            return []

        now = datetime.utcnow()
        cooldown_border = now - timedelta(seconds=60)
        is_local = AIService._is_local_provider(provider)

        available: List[APIKey] = []

        for key in keys:
            if not key.is_active:
                continue

            normalized = APIKeyRepository.normalize_api_key(key.api_key)
            placeholder = APIKeyRepository._is_placeholder_key(key.api_key)

            if placeholder and not is_local:
                await api_key_repo.deactivate(key.id)
                await api_key_repo.set_error(key.id, "Placeholder API key disabled automatically")
                continue

            if not normalized and not is_local:
                await api_key_repo.deactivate(key.id)
                await api_key_repo.set_error(key.id, "Empty API key disabled automatically")
                continue

            if (
                key.last_error
                and key.updated_at
                and key.updated_at > cooldown_border
                and AIService._is_rate_limit_error(key.last_error)
            ):
                continue

            available.append(key)

        return available

    @staticmethod
    async def _available_models_for_provider(
        model_repo: AIModelRepository,
        provider_id: int,
    ) -> List[AIModel]:
        models = await model_repo.get_by_provider(provider_id)
        active_models = [model for model in models if model.is_active]
        if not active_models:
            return []

        active_models.sort(
            key=lambda item: (
                0 if item.is_default else 1,
                item.last_used_at or datetime.min,
                item.created_at,
            )
        )
        return active_models

    @staticmethod
    async def _build_candidates(
        provider_id: Optional[int] = None,
        exclude_provider_ids: Optional[Set[int]] = None,
    ) -> List[_Candidate]:
        async with get_session() as session:
            ai_provider_repo = AIProviderRepository(session)
            api_key_repo = APIKeyRepository(session)
            model_repo = AIModelRepository(session)

            providers = await AIService._ordered_providers(
                ai_provider_repo=ai_provider_repo,
                provider_id=provider_id,
                exclude_provider_ids=exclude_provider_ids,
            )

            candidates: List[_Candidate] = []
            for provider in providers:
                keys = await AIService._available_keys_for_provider(api_key_repo, provider)
                models = await AIService._available_models_for_provider(model_repo, provider.id)

                if not keys or not models:
                    continue

                for key in keys:
                    for model in models:
                        candidates.append(_Candidate(provider=provider, api_key=key, model=model))

            return candidates

    @staticmethod
    async def get_service(provider_id: Optional[int] = None) -> Optional["AIService"]:
        candidates = await AIService._build_candidates(provider_id=provider_id)
        if not candidates:
            logger.error("No active AI candidates found")
            return None

        first = candidates[0]
        logger.info(
            "AI selected: provider=%s key=%s model=%s",
            first.provider.name,
            AIService._safe_key_name(first.api_key),
            first.model.model_name,
        )
        return AIService(first.provider, first.api_key, first.model)

    @staticmethod
    async def try_next_key_or_provider(
        exclude_provider_ids: Optional[Set[int]] = None,
    ) -> Optional["AIService"]:
        candidates = await AIService._build_candidates(
            exclude_provider_ids=exclude_provider_ids
        )
        if not candidates:
            return None
        first = candidates[0]
        return AIService(first.provider, first.api_key, first.model)

    async def _touch_success(self) -> None:
        async with get_session() as session:
            api_key_repo = APIKeyRepository(session)
            model_repo = AIModelRepository(session)
            await api_key_repo.update_usage(self.api_key.id)
            await model_repo.update_last_used(self.model.id)

    async def _record_key_error(self, error_message: str) -> None:
        async with get_session() as session:
            api_key_repo = APIKeyRepository(session)
            await api_key_repo.set_error(self.api_key.id, error_message[:500])
            if self._is_auth_error(error_message) and not self._is_local_provider(self.provider):
                await api_key_repo.deactivate(self.api_key.id)
                logger.warning(
                    "Deactivated key %s for provider %s due to auth error",
                    self.api_key.id,
                    self.provider.name,
                )

    async def _record_model_error(self, error_message: str, bot=None) -> None:
        async with get_session() as session:
            model_repo = AIModelRepository(session)
            await model_repo.record_error(self.model.id, error_message[:500])

            if self._is_model_error(error_message):
                await model_repo.deactivate(self.model.id)
                logger.warning(
                    "Deactivated model %s for provider %s: %s",
                    self.model.model_name,
                    self.provider.name,
                    error_message[:200],
                )
                if bot:
                    await self._notify_all_admins(
                        bot,
                        (
                            "AI model disabled automatically.\n"
                            f"Provider: {self.provider.display_name}\n"
                            f"Model: {self.model.model_name}\n"
                            f"Reason: {error_message[:200]}"
                        ),
                    )

    async def _notify_all_admins(self, bot, message: str) -> None:
        from services.thread_service import ThreadService

        try:
            thread_service = ThreadService(bot)
            await thread_service.send_log_message(message)
        except Exception as error:
            logger.error("Failed to send log message: %s", error)

    async def _reset_key_limit_if_needed(self) -> None:
        if not self.api_key.limit_reset_at:
            return
        if self.api_key.limit_reset_at > datetime.utcnow():
            return

        async with get_session() as session:
            api_key_repo = APIKeyRepository(session)
            await api_key_repo.reset_limit(
                self.api_key.id,
                datetime.utcnow() + timedelta(hours=24),
            )

    async def _stream_once(
        self,
        full_messages: List[Dict[str, str]],
    ) -> AsyncGenerator[str, None]:
        async with self._request_semaphore:
            await self._reset_key_limit_if_needed()
            stream = await self.client.chat.completions.create(
                model=self.model.model_name,
                messages=full_messages,
                temperature=0.7,
                max_tokens=1024,
                stream=True,
            )

        yielded = False
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yielded = True
                yield delta

        if not yielded:
            raise RuntimeError("Empty streamed response")

    async def _completion_once(self, full_messages: List[Dict[str, str]]) -> str:
        async with self._request_semaphore:
            await self._reset_key_limit_if_needed()
            completion = await self.client.chat.completions.create(
                model=self.model.model_name,
                messages=full_messages,
                temperature=0.7,
                max_tokens=1024,
            )

        text = completion.choices[0].message.content or ""
        if not text.strip():
            raise RuntimeError("Empty completion response")
        return text

    async def _build_failover_chain(
        self,
        attempted_provider_ids: Optional[Set[int]] = None,
    ) -> List[_Candidate]:
        chain: List[_Candidate] = []
        seen: Set[Tuple[int, int, int]] = set()

        def push(candidate: _Candidate) -> None:
            key = (candidate.provider.id, candidate.api_key.id, candidate.model.id)
            if key in seen:
                return
            seen.add(key)
            chain.append(candidate)

        push(_Candidate(provider=self.provider, api_key=self.api_key, model=self.model))

        same_provider_candidates = await self._build_candidates(provider_id=self.provider.id)
        for candidate in same_provider_candidates:
            push(candidate)

        exclude = set(attempted_provider_ids or set())
        exclude.add(self.provider.id)
        other_candidates = await self._build_candidates(exclude_provider_ids=exclude)
        for candidate in other_candidates:
            push(candidate)

        return chain

    async def get_system_prompt(
        self,
        training_repo: TrainingRepository,
        language: str = "ru",
    ) -> str:
        training_messages = await training_repo.get_all_active()

        descriptions = {
            "ru": "CartaMe helps users keep discount cards in one QR code.",
            "en": "CartaMe helps users keep discount cards in one QR code.",
            "uz": "CartaMe helps users keep discount cards in one QR code.",
            "kz": "CartaMe helps users keep discount cards in one QR code.",
        }
        description = descriptions.get(language, descriptions["en"])

        prompt = (
            "You are CartaMe support AI assistant.\n\n"
            f"Service: {description}\n\n"
            "Rules:\n"
            "- Company name must be exactly CartaMe.\n"
            "- No emojis.\n"
            f"- Respond only in language code: {language}.\n"
            "- Keep responses concise, clear, and factual.\n"
            "- If question is not about CartaMe service/support/cards/qr, answer exactly: ignore_offtopic\n"
            "- If issue requires human support and cannot be solved safely, append token call_people\n"
            "\nClarifications:\n"
            "- Treat mentions of cards, discount/loyalty cards, QR codes, barcodes, and related terms as on-topic.\n"
            "- Treat these as CartaMe mentions too: CaraMe, Kartame, Carta Me (common misspellings).\n"
            "- For Russian/Kazakh/Uzbek: words like карта/карты/картами/скидка/дисконт/штрихкод/QR are on-topic.\n"
        )

        for message in training_messages:
            if message.role == "system" and message.content.strip():
                prompt += f"\n\n{message.content.strip()}"

        return prompt

    async def is_relevant_question(self, question: str) -> bool:
        try:
            answer = await self.get_response(
                messages=[{"role": "user", "content": question}],
                system_prompt=(
                    "Answer only yes or no. Is this question related to CartaMe support, "
                    "discount cards, QR codes, app registration, or app usage?"
                ),
            )
            return "yes" in answer.lower()
        except Exception:
            return True

    async def get_response_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        user_id: int = None,
        thread_id: int = None,
        bot=None,
        attempted_provider_ids: Optional[Set[int]] = None,
    ) -> AsyncGenerator[str, None]:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        chain = await self._build_failover_chain(attempted_provider_ids=attempted_provider_ids)
        last_error = ""

        for candidate in chain:
            service = AIService(candidate.provider, candidate.api_key, candidate.model)
            started_stream = False

            try:
                logger.info(
                    "AI attempt stream: provider=%s key=%s model=%s",
                    service.provider.name,
                    self._safe_key_name(service.api_key),
                    service.model.model_name,
                )
                async for chunk in service._stream_once(full_messages):
                    started_stream = True
                    yield chunk

                await service._touch_success()
                return

            except (RateLimitError, APIError, Exception) as error:
                last_error = str(error)
                logger.warning(
                    "AI stream error: provider=%s key=%s model=%s error=%s",
                    service.provider.name,
                    self._safe_key_name(service.api_key),
                    service.model.model_name,
                    last_error,
                )

                if started_stream:
                    await service._record_key_error(last_error)
                    return

                if service._is_model_error(last_error):
                    await service._record_model_error(last_error, bot=bot)
                else:
                    await service._record_key_error(last_error)
                continue

        if bot:
            try:
                from services.thread_service import ThreadService

                thread_service = ThreadService(bot)
                await thread_service.send_log_message(
                    (
                        "AI unavailable across all providers. "
                        f"user_id={user_id} thread_id={thread_id} error={last_error[:200]}"
                    )
                )
            except Exception:
                pass

        yield "AI service is temporarily unavailable. Please try again later."

    async def get_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        bot=None,
        attempted_provider_ids: Optional[Set[int]] = None,
    ) -> str:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        chain = await self._build_failover_chain(attempted_provider_ids=attempted_provider_ids)
        last_error = ""

        for candidate in chain:
            service = AIService(candidate.provider, candidate.api_key, candidate.model)
            try:
                logger.info(
                    "AI attempt completion: provider=%s key=%s model=%s",
                    service.provider.name,
                    self._safe_key_name(service.api_key),
                    service.model.model_name,
                )
                text = await service._completion_once(full_messages)
                await service._touch_success()
                return text
            except (RateLimitError, APIError, Exception) as error:
                last_error = str(error)
                logger.warning(
                    "AI completion error: provider=%s key=%s model=%s error=%s",
                    service.provider.name,
                    self._safe_key_name(service.api_key),
                    service.model.model_name,
                    last_error,
                )
                if service._is_model_error(last_error):
                    await service._record_model_error(last_error, bot=bot)
                else:
                    await service._record_key_error(last_error)
                continue

        if bot:
            try:
                from services.thread_service import ThreadService

                thread_service = ThreadService(bot)
                await thread_service.send_log_message(
                    f"AI unavailable across all providers. error={last_error[:200]}"
                )
            except Exception:
                pass

        return "AI service is temporarily unavailable. Please try again later."

    async def cluster_questions(self, questions: List[str]) -> List[Dict]:
        if not questions:
            return []

        sample = [q.strip() for q in questions[:120] if q and q.strip()]
        if not sample:
            return []

        prompt = (
            "Group similar user questions into short categories.\n"
            "Return each category on a new line in format: Category name (count).\n\n"
            + "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(sample))
        )

        try:
            response = await self.get_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are analytics assistant. Return only list of grouped categories.",
            )
            lines = [line.strip(" -•\t") for line in response.splitlines() if line.strip()]
            return [{"description": line} for line in lines[:20]]
        except Exception as error:
            logger.warning("Question clustering failed: %s", error)
            return []
