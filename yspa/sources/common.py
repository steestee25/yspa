import calendar
import re
from datetime import datetime, timezone
from html import unescape

import httpx

TIMEOUT = httpx.Timeout(20.0)
_TAG = re.compile(r"<[^>]+>")


def http_get(url: str, user_agent: str = "yspa/0.1", params: dict | None = None) -> httpx.Response:
    response = httpx.get(url, params=params, headers={"User-Agent": user_agent}, timeout=TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    return response


def strip_html(html: str) -> str:
    return " ".join(unescape(_TAG.sub(" ", html or "")).split())


def struct_time_to_iso(st) -> str:
    """Converte la data di feedparser (UTC) in ISO; usa l'ora attuale se manca."""
    if not st:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    return datetime.fromtimestamp(calendar.timegm(st), timezone.utc).isoformat(timespec="seconds")
