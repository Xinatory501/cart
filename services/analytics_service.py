import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from html import escape
from typing import Dict, List, Optional, Tuple

from database.repository import AdminRepository
from services.ai_service import AIService

logger = logging.getLogger(__name__)


class AnalyticsService:
    _BRAND_PATTERNS = [
        (r"\b(carta\s*me|cartame|cara\s*me|carame|kartame|karta\s*me)\b", "cartame"),
        (r"\b(картаме|картами|карта\s*ме|кара\s*ме|карта\s*ми)\b", "cartame"),
    ]

    @classmethod
    def _normalize_brand_terms(cls, text: str) -> str:
        normalized = text
        for pattern, replacement in cls._BRAND_PATTERNS:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        return normalized

    @staticmethod
    def _normalize_question(text: str) -> str:
        normalized = text.lower().strip()
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = AnalyticsService._normalize_brand_terms(normalized)
        normalized = re.sub(r"[^\w\sа-яА-ЯёЁ?]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _aggregate_questions(self, questions: List[str], limit: int = 10) -> List[Tuple[str, int]]:
        if not questions:
            return []

        grouped: Dict[str, Tuple[str, int]] = {}
        counter: Counter[str] = Counter()

        for item in questions:
            raw = item.strip()
            if not raw:
                continue

            key = self._normalize_question(raw)
            if not key:
                continue

            counter[key] += 1
            if key not in grouped:
                grouped[key] = (raw, 1)

        ranked = counter.most_common(limit)
        return [(grouped[key][0], count) for key, count in ranked]

    async def _build_ai_answered_topics(
        self,
        ai_questions: List[str],
        ai_service: Optional[AIService],
    ) -> List[str]:
        if not ai_questions:
            return []

        if ai_service:
            try:
                clusters = await ai_service.cluster_questions(ai_questions[:120])
                parsed = []
                for cluster in clusters:
                    text = (cluster.get("description") or "").strip()
                    if text:
                        parsed.append(text)
                if parsed:
                    return parsed[:10]
            except Exception as error:
                logger.warning("AI clustering failed; fallback enabled: %s", error)

        aggregated = self._aggregate_questions(ai_questions, limit=10)
        return [f"{question} ({count})" for question, count in aggregated]

    async def generate_report(
        self,
        admin_repo: AdminRepository,
        ai_service: Optional[AIService],
        start_date: datetime,
        end_date: datetime,
    ) -> str:
        user_count = await admin_repo.get_user_count_by_period(start_date, end_date)
        message_count = await admin_repo.get_message_count_by_period(start_date, end_date)

        all_questions = await admin_repo.get_questions_by_period(
            start_date,
            end_date,
            limit=2000,
            ai_only=False,
        )
        ai_answered_questions = await admin_repo.get_questions_by_period(
            start_date,
            end_date,
            limit=2000,
            ai_only=True,
        )

        ai_topics = await self._build_ai_answered_topics(ai_answered_questions, ai_service)
        popular_questions = self._aggregate_questions(all_questions, limit=10)

        def safe_text(value: str, max_len: int = 180) -> str:
            cleaned = (value or "").strip().replace("\n", " ")
            if len(cleaned) > max_len:
                cleaned = cleaned[: max_len - 1] + "…"
            return escape(cleaned)

        report = (
            "📊 <b>Отчет за период</b>\n\n"
            f"📅 Период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}\n\n"
            "📈 <b>Метрики:</b>\n"
            f"• Сообщений всего: {message_count}\n"
            f"• Пользователей за период: {user_count}\n"
            f"• Вопросов пользователей: {len(all_questions)}\n"
            f"• Вопросов, обработанных AI: {len(ai_answered_questions)}\n"
        )

        report += "\n🤖 <b>Вопросы, на которые отвечала нейросеть (похожие объединены):</b>\n"
        if ai_topics:
            for idx, topic in enumerate(ai_topics, 1):
                report += f"{idx}. {safe_text(topic)}\n"
        else:
            report += "Нет данных за выбранный период.\n"

        report += "\n🔥 <b>Самые популярные вопросы:</b>\n"
        if popular_questions:
            for idx, (question, count) in enumerate(popular_questions, 1):
                report += f"{idx}. {safe_text(question)} — {count}\n"
        else:
            report += "Нет данных за выбранный период.\n"

        if len(report) > 3900:
            report = report[:3890] + "\n…"

        return report

    @staticmethod
    def get_period_dates(period: str) -> tuple[datetime, datetime]:
        now = datetime.utcnow()

        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == "week":
            start = now - timedelta(days=7)
            end = now
        elif period == "month":
            start = now - timedelta(days=30)
            end = now
        else:
            start = now - timedelta(days=7)
            end = now

        return start, end
