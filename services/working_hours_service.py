"""
Working hours service.

Stores schedule in ConfigRepository under key "working_hours_config" as JSON:
{
    "enabled": true,
    "timezone": "Europe/Minsk",
    "schedules": [
        {"days": [1, 2, 3, 4, 5], "start": "09:00", "end": "17:00"}
    ],
    "holidays": ["2025-01-01", "2025-01-07"]
}

Days: 0=Monday, 1=Tuesday, ..., 6=Sunday  (Python weekday() convention)
"""

import json
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Europe/Minsk"

DEFAULT_CONFIG = {
    "enabled": False,
    "timezone": DEFAULT_TIMEZONE,
    "schedules": [],
    "holidays": [],
}

DAY_NAMES_RU = {
    0: "понедельник",
    1: "вторник",
    2: "среду",
    3: "четверг",
    4: "пятницу",
    5: "субботу",
    6: "воскресенье",
}

DAY_NAMES_EN = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

DAY_NAMES_UZ = {
    0: "dushanba",
    1: "seshanba",
    2: "chorshanba",
    3: "payshanba",
    4: "juma",
    5: "shanba",
    6: "yakshanba",
}

DAY_NAMES_KZ = {
    0: "дүйсенбі",
    1: "сейсенбі",
    2: "сәрсенбі",
    3: "бейсенбі",
    4: "жұма",
    5: "сенбі",
    6: "жексенбі",
}

DAY_NAMES = {
    "ru": DAY_NAMES_RU,
    "en": DAY_NAMES_EN,
    "uz": DAY_NAMES_UZ,
    "kz": DAY_NAMES_KZ,
}


async def _load_config() -> dict:
    """Load working hours config from DB."""
    try:
        from database.database import get_session
        from database.repository import ConfigRepository

        async with get_session() as session:
            config_repo = ConfigRepository(session)
            raw = await config_repo.get("working_hours_config")

        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("working_hours: failed to load config: %s", exc)

    return dict(DEFAULT_CONFIG)


async def save_config(config: dict) -> None:
    """Save working hours config to DB."""
    from database.database import get_session
    from database.repository import ConfigRepository

    async with get_session() as session:
        config_repo = ConfigRepository(session)
        await config_repo.set(
            "working_hours_config",
            json.dumps(config, ensure_ascii=False),
            description="Рабочее время операторов (JSON)",
        )


def _get_tz(timezone: str):
    """Get timezone object, falling back to Europe/Minsk."""
    try:
        import pytz
        return pytz.timezone(timezone)
    except Exception:
        import pytz
        return pytz.timezone(DEFAULT_TIMEZONE)


def _check_schedule(config: dict) -> tuple[bool, Optional[dict]]:
    """
    Returns (is_available, next_schedule_entry).
    next_schedule_entry is the schedule that will open next (or current open schedule).
    """
    if not config.get("enabled"):
        return True, None  # Feature disabled → always available

    tz = _get_tz(config.get("timezone", DEFAULT_TIMEZONE))
    now = datetime.now(tz)
    today = now.date()
    today_str = today.strftime("%Y-%m-%d")
    weekday = today.weekday()  # 0=Monday … 6=Sunday
    current_time = now.strftime("%H:%M")

    # Check holidays first
    holidays = config.get("holidays", [])
    if today_str in holidays:
        return False, None

    schedules = config.get("schedules", [])
    if not schedules:
        return True, None  # No schedules configured → always available

    for schedule in schedules:
        days = schedule.get("days", [])
        start = schedule.get("start", "00:00")
        end = schedule.get("end", "23:59")

        if weekday in days and start <= current_time <= end:
            return True, schedule

    return False, None


async def is_operator_available() -> bool:
    """Returns True if operators are currently available."""
    config = await _load_config()
    available, _ = _check_schedule(config)
    return available


async def get_next_shift_info(language: str = "ru") -> str:
    """
    Returns a human-readable string like 'в понедельник в 09:00' describing
    the next shift start. Returns empty string if not determinable.
    """
    config = await _load_config()

    if not config.get("enabled"):
        return ""

    tz = _get_tz(config.get("timezone", DEFAULT_TIMEZONE))
    now = datetime.now(tz)
    today = now.date()
    current_time = now.strftime("%H:%M")
    weekday = today.weekday()

    schedules = config.get("schedules", [])
    if not schedules:
        return ""

    holidays = config.get("holidays", [])

    day_names = DAY_NAMES.get(language, DAY_NAMES_RU)

    # Look ahead up to 7 days to find next shift
    for offset in range(0, 8):
        from datetime import timedelta
        check_date = today + timedelta(days=offset)
        check_str = check_date.strftime("%Y-%m-%d")
        check_weekday = check_date.weekday()

        if check_str in holidays:
            continue

        for schedule in schedules:
            days = schedule.get("days", [])
            start = schedule.get("start", "09:00")

            if check_weekday not in days:
                continue

            # Same day: only if the shift hasn't started yet
            if offset == 0 and current_time >= start:
                continue

            day_label = day_names.get(check_weekday, str(check_weekday))

            if language == "ru":
                if offset == 0:
                    return f"сегодня в {start}"
                elif offset == 1:
                    return f"завтра в {start}"
                else:
                    return f"в {day_label} в {start}"
            elif language == "uz":
                if offset == 0:
                    return f"bugun soat {start} da"
                elif offset == 1:
                    return f"ertaga soat {start} da"
                else:
                    return f"{day_label} soat {start} da"
            elif language == "kz":
                if offset == 0:
                    return f"бүгін сағат {start}-де"
                elif offset == 1:
                    return f"ертең сағат {start}-де"
                else:
                    return f"{day_label} сағат {start}-де"
            else:  # en
                if offset == 0:
                    return f"today at {start}"
                elif offset == 1:
                    return f"tomorrow at {start}"
                else:
                    return f"on {day_label} at {start}"

    return ""


async def get_working_hours_status_text() -> str:
    """
    Returns a formatted status string for the admin panel.
    """
    config = await _load_config()
    enabled = config.get("enabled", False)
    timezone = config.get("timezone", DEFAULT_TIMEZONE)
    schedules = config.get("schedules", [])
    holidays = config.get("holidays", [])

    lines = [
        "🕐 <b>Время работы операторов</b>\n",
        f"Статус: {'✅ Включено' if enabled else '❌ Выключено'}",
        f"Часовой пояс: <code>{timezone}</code>",
    ]

    if schedules:
        lines.append("\n<b>Расписания:</b>")
        day_ru = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
        for s in schedules:
            day_nums = s.get("days", [])
            day_str = ", ".join(day_ru.get(d, str(d)) for d in sorted(day_nums))
            lines.append(f"  • {day_str}: {s['start']} – {s['end']}")
    else:
        lines.append("\n<b>Расписания:</b> не настроены")

    if holidays:
        lines.append("\n<b>Выходные/праздники:</b>")
        for h in sorted(holidays):
            lines.append(f"  • {h}")
    else:
        lines.append("<b>Выходные:</b> не заданы")

    return "\n".join(lines)
