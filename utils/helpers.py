
from typing import Optional

def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def format_user_display(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> str:
    if username:
        return f"@{username}"
    elif first_name:
        return f"{first_name} (ID: {user_id})"
    else:
        return f"User (ID: {user_id})"

def truncate_text(text: str, max_length: int = 100) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
