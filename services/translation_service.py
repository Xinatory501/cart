"""
Translation service for operator interface.

Uses the existing AIService (same AI provider as the chat)
to translate text between languages without needing a separate API key.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Language names for prompts
_LANG_NAMES = {
    "ru": "Russian",
    "en": "English",
    "uz": "Uzbek",
    "kz": "Kazakh",
}

TEMPLATES = {
    "greeting": {
        "title": "👋 Приветствие",
        "ru": "Здравствуйте! Чем я могу вам помочь?",
        "en": "Hello! How can I help you?",
        "uz": "Assalomu alaykum! Sizga qanday yordam bera olaman?",
        "kz": "Сәлеметсіз бе! Сізге қалай көмектесе аламын?"
    },
    "verification_24h": {
        "title": "⏳ Чек в обработке (24ч)",
        "ru": "Ваш чек находится в обработке. Обычно проверка занимает до 24 часов.",
        "en": "Your receipt is processing. Verification usually takes up to 24 hours.",
        "uz": "Sizning chegingiz qayta ishlanmoqda. Odatda tekshirish 24 soatgacha davom etadi.",
        "kz": "Сіздің чегіңіз өңделіп жатыр. Әдетте тексеру 24 сағатқа дейін созылады."
    },
    "bad_quality": {
        "title": "📷 Плохое качество чека",
        "ru": "Пожалуйста, отправьте чек повторно в хорошем качестве, чтобы все данные были четко видны.",
        "en": "Please resend the receipt in good quality so that all data is clearly visible.",
        "uz": "Iltimos, barcha ma'lumotlar aniq ko'rinishi uchun chekni sifatli formatda qaytadan yuboring.",
        "kz": "Барлық деректер анық көрінуі үшін чекті жақсы сапада қайта жіберіңіз."
    },
    "success": {
        "title": "✅ Чек успешно начислен",
        "ru": "Ваш чек успешно проверен и начислен. Проверьте баланс в приложении.",
        "en": "Your receipt has been successfully verified and credited. Please check your balance in the app.",
        "uz": "Sizning chegingiz muvaffaqiyatli tekshirildi va hisobga olindi. Ilovada balansingizni tekshiring.",
        "kz": "Сіздің чегіңіз сәтті тексеріліп, есептелді. Қолданбадағы теңгерімді тексеріңіз."
    },
    "ask_details": {
        "title": "🔍 Запросить Loyalty ID",
        "ru": "Пожалуйста, опишите вашу проблему более подробно и укажите ваш Loyalty ID.",
        "en": "Please describe your issue in more detail and specify your Loyalty ID.",
        "uz": "Iltimos, muammoingizni batafsilroq tasvirlab bering va Loyalty ID-ingizni ko'rsating.",
        "kz": "Мәселеңізді толығырақ сипаттап, Loyalty ID-іңізді көрсетіңіз."
    }
}


# Pending translations store: { (thread_id, msg_id): TranslationDraft }
# In-memory dict — lives for the lifetime of the bot process.
# Keyed by (thread_id, prompt_message_id) to allow one pending draft per prompt message.
_pending: dict[tuple[int, int], "TranslationDraft"] = {}


class TranslationDraft:
    """Holds a pending translation waiting for operator confirmation."""

    __slots__ = ("user_id", "thread_id", "original_text", "translated_text", "user_lang", "send_both")

    def __init__(
        self,
        user_id: int,
        thread_id: int,
        original_text: str,
        translated_text: str,
        user_lang: str,
        send_both: bool = False,
    ):
        self.user_id = user_id
        self.thread_id = thread_id
        self.original_text = original_text
        self.translated_text = translated_text
        self.user_lang = user_lang
        self.send_both = send_both


def store_draft(thread_id: int, prompt_msg_id: int, draft: TranslationDraft) -> None:
    _pending[(thread_id, prompt_msg_id)] = draft


def get_draft(thread_id: int, prompt_msg_id: int) -> Optional[TranslationDraft]:
    return _pending.get((thread_id, prompt_msg_id))


def remove_draft(thread_id: int, prompt_msg_id: int) -> None:
    _pending.pop((thread_id, prompt_msg_id), None)


def update_draft_translation(thread_id: int, prompt_msg_id: int, new_text: str) -> None:
    draft = _pending.get((thread_id, prompt_msg_id))
    if draft:
        draft.translated_text = new_text


async def translate_text(text: str, target_lang: str, source_lang: str = "auto") -> Optional[str]:
    """
    Translate `text` to `target_lang` using the configured AI provider.
    Returns translated text or None on failure.
    """
    from services.ai_service import AIService

    ai_service = await AIService.get_service()
    if not ai_service:
        logger.error("translation: AI service unavailable")
        return None

    lang_name = _LANG_NAMES.get(target_lang, target_lang)

    system_prompt = (
        f"You are a professional translator. "
        f"Translate the following text to {lang_name}. "
        f"Output ONLY the translation — no explanations, no quotes, no prefixes."
    )

    messages = [{"role": "user", "content": text}]

    try:
        result = await ai_service.get_response(messages=messages, system_prompt=system_prompt)
        return (result or "").strip()
    except Exception as exc:
        logger.error("translation: failed to translate: %s", exc)
        return None


async def get_send_both_setting() -> bool:
    """
    Return True if operator reply should include both translation + original Russian text.
    Configured via admin panel, stored in ConfigRepository as 'translation_send_both'.
    """
    try:
        from database.database import get_session
        from database.repository import ConfigRepository

        async with get_session() as session:
            config_repo = ConfigRepository(session)
            val = await config_repo.get("translation_send_both")
            return val == "1"
    except Exception:
        return False


async def set_send_both_setting(value: bool) -> None:
    """Save the send_both setting."""
    from database.database import get_session
    from database.repository import ConfigRepository

    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.set(
            "translation_send_both",
            "1" if value else "0",
            description="Отправлять перевод + оригинал оператора (1) или только перевод (0)",
        )
