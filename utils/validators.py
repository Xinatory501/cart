
import re
from typing import Optional

def is_valid_url(url: str) -> bool:
    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    return url_pattern.match(url) is not None

def is_valid_telegram_id(user_id: int) -> bool:
    return user_id > 0 and user_id < 10**12

def parse_user_identifier(identifier: str) -> Optional[int]:
    identifier = identifier.strip().lstrip('@')

    try:
        user_id = int(identifier)
        if is_valid_telegram_id(user_id):
            return user_id
    except ValueError:
        pass

    return None
