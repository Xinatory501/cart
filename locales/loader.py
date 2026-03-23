
import json
import os
from typing import Dict

LOCALES_DIR = os.path.dirname(__file__)
SUPPORTED_LANGUAGES = ["en", "ru", "uz", "kz"]

_translations: Dict[str, Dict] = {}

def load_translations():
    global _translations

    for lang in SUPPORTED_LANGUAGES:
        file_path = os.path.join(LOCALES_DIR, f"{lang}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                _translations[lang] = json.load(f)

def get_text(key: str, language: str = "en", **kwargs) -> str:
    if not _translations:
        load_translations()

    if language not in _translations:
        language = "en"

    text = _translations.get(language, {}).get(key, f"[{key}]")

    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass

    return text

load_translations()
