"""Orari leggibili: "oggi 15:15", "ieri 18:02", "24 ott 09:10"."""
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import config

MONTHS = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]


def human_time(iso: str | None, now: datetime | None = None) -> str:
    if not iso:
        return ""
    tz = ZoneInfo(config.TIMEZONE)
    when = datetime.fromisoformat(iso).astimezone(tz)
    today = (now or datetime.now(tz)).astimezone(tz).date()
    days = (today - when.date()).days
    clock = when.strftime("%H:%M")
    if days == 0:
        return f"oggi {clock}"
    if days == 1:
        return f"ieri {clock}"
    label = f"{when.day} {MONTHS[when.month - 1]}"
    return f"{label} {clock}" if when.year == today.year else f"{label} {when.year}"
