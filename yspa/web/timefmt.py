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


def calm_title(title: str) -> str:
    """Un titolo tutto in maiuscolo diventa 'Frase normale': in un elenco sobrio, il maiuscolo urla."""
    letters = [c for c in title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        lowered = title.lower()
        return lowered[:1].upper() + lowered[1:]
    return title
