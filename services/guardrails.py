"""
AI-11: PII Masking — минимизация контекста и редакция PII перед отправкой в AI.
AI-12: Guardrails — защита от prompt injection и unsafe content.
"""
from __future__ import annotations

import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# ─── PII Patterns ──────────────────────────────────────────────────────────────
_PHONE_RE = re.compile(r'\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')
_EMAIL_RE = re.compile(r'[\w.+\-]+@[\w\-]+\.[\w.]+')
_CARD_RE  = re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b')
_CVV_RE   = re.compile(r'\bcvv[\s:=]?\d{3,4}\b', re.IGNORECASE)
_LOYALTY_RE = re.compile(r'\b\d{8,16}\b')   # Loyalty card / account IDs
_USERNAME_RE = re.compile(r'@[A-Za-z0-9_]{4,}')
_PASSWORD_RE = re.compile(r'(?i)(password|пароль|pass|pwd)[\s:=]+\S+')
_IIN_RE   = re.compile(r'\b\d{12}\b')        # Казахстанский ИИН

# Инструкции системного промпта — запрещаем их перезапись
_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(all\s+)?previous\s+(instructions?|prompt)', re.IGNORECASE),
    re.compile(r'forget\s+(all\s+)?(your\s+)?(previous\s+)?(instructions?|context)', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+a', re.IGNORECASE),
    re.compile(r'act\s+as\s+(a\s+)?(different|new|uncensored)', re.IGNORECASE),
    re.compile(r'DAN\s+mode', re.IGNORECASE),
    re.compile(r'jailbreak', re.IGNORECASE),
    re.compile(r'system\s*prompt\s*:', re.IGNORECASE),
    re.compile(r'\[INST\]|\[\/INST\]|<\|system\|>|<\|user\|>|<\|assistant\|>'),
    re.compile(r'reveal\s+(your\s+)?(system\s+)?prompt', re.IGNORECASE),
    re.compile(r'show\s+me\s+your\s+(instructions?|prompt)', re.IGNORECASE),
]

# Unsafe content markers
_UNSAFE_PATTERNS = [
    re.compile(r'(?i)(bomb|weapon|explosive|terrorist|synthesize\s+drug)', re.IGNORECASE),
    re.compile(r'(?i)how\s+to\s+(hack|crack|bypass\s+security)', re.IGNORECASE),
]


def redact_pii(text: str, replace_with_hash: bool = False) -> str:
    """
    AI-11: Redact PII from user message before sending to external AI.
    If replace_with_hash=True, use pseudonymous hash instead of placeholder.
    """
    if not text:
        return text

    def _replace(pattern: re.Pattern, label: str) -> None:
        nonlocal text
        if replace_with_hash:
            def _hasher(m: re.Match) -> str:
                import hashlib
                h = hashlib.sha256(m.group().encode()).hexdigest()[:8]
                return f'[{label}:{h}]'
            text = pattern.sub(_hasher, text)
        else:
            text = pattern.sub(f'[{label}]', text)

    _replace(_IIN_RE, 'IIN')         # ИИН first (12 digits, before LOYALTY)
    _replace(_CARD_RE, 'CARD')
    _replace(_CVV_RE, 'CVV')
    _replace(_LOYALTY_RE, 'ID')
    _replace(_PHONE_RE, 'PHONE')
    _replace(_EMAIL_RE, 'EMAIL')
    _replace(_USERNAME_RE, 'USER')
    _replace(_PASSWORD_RE, 'PASSWORD')

    return text


def check_injection(text: str) -> bool:
    """
    AI-12: Returns True if the text looks like a prompt injection attempt.
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning("Prompt injection detected: %s", text[:100])
            return True
    return False


def check_unsafe_content(text: str) -> bool:
    """
    AI-12: Returns True if text contains unsafe/harmful requests.
    """
    for pattern in _UNSAFE_PATTERNS:
        if pattern.search(text):
            logger.warning("Unsafe content detected: %s", text[:100])
            return True
    return False


def sanitize_messages_for_ai(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Apply PII redaction to all user messages before sending to external AI provider.
    System messages are NOT redacted (they are internal prompts).
    """
    result = []
    for msg in messages:
        if msg.get('role') == 'user':
            cleaned = redact_pii(msg['content'])
            result.append({**msg, 'content': cleaned})
        else:
            result.append(msg)
    return result


def is_safe_user_message(text: str) -> tuple[bool, str]:
    """
    Returns (is_safe, reason). Use before processing user message.
    """
    if check_injection(text):
        return False, 'prompt_injection'
    if check_unsafe_content(text):
        return False, 'unsafe_content'
    return True, ''
