"""SEC EDGAR: depositi ufficiali appena pubblicati (gratuito, quasi in tempo reale)."""
import json
import re
import time
from pathlib import Path

import feedparser

from .. import config
from .common import http_get, strip_html, struct_time_to_iso

CURRENT_FEED = "https://www.sec.gov/cgi-bin/browse-edgar"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
TICKERS_CACHE_MAX_AGE = 24 * 3600

# "8-K - Moderna, Inc. (0001682852) (Filer)"
_TITLE = re.compile(r"^(?P<form>[^ ]+(?: [^ ]+)?) - (?P<company>.+?) \((?P<cik>\d{10})\) \((?P<role>[^)]+)\)")
_ITEM = re.compile(r"Item (\d\.\d\d)")


def _require_user_agent() -> str:
    if not config.SEC_USER_AGENT:
        raise RuntimeError("Imposta YSPA_SEC_USER_AGENT (es. 'Mario Rossi mario@esempio.com'): la SEC lo richiede.")
    return config.SEC_USER_AGENT


def load_cik_to_ticker(cache_path: Path | None = None) -> dict[int, str]:
    """Mappa CIK -> ticker, scaricata dalla SEC e salvata in cache per un giorno."""
    cache_path = cache_path or config.DB_PATH.parent / "sec_tickers.json"
    if not cache_path.exists() or time.time() - cache_path.stat().st_mtime > TICKERS_CACHE_MAX_AGE:
        data = http_get(TICKERS_URL, _require_user_agent()).json()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data))
    data = json.loads(cache_path.read_text())
    return {int(row["cik_str"]): row["ticker"] for row in data.values()}


def parse_feed(xml: str, cik_to_ticker: dict[int, str]) -> list[dict]:
    items = []
    for entry in feedparser.parse(xml).entries:
        match = _TITLE.match(entry.get("title", ""))
        if not match:
            continue
        # Nei 13D compaiono due voci: chi deposita ("Filed by") e l'azienda interessata ("Subject").
        # Teniamo solo l'azienda interessata, e per gli altri moduli chi deposita ("Filer").
        if match["role"] == "Filed by":
            continue
        summary = strip_html(entry.get("summary", ""))
        ticker = cik_to_ticker.get(int(match["cik"]))
        items.append({
            "uid": f"sec:{entry.get('id', entry.get('link'))}:{match['cik']}",
            "source": f"SEC {match['form']}",
            "title": f"{match['form']} – {match['company']}",
            "summary": summary,
            "url": entry.get("link", ""),
            "published_at": struct_time_to_iso(entry.get("updated_parsed")),
            "tickers": [ticker] if ticker else [],
            "sec_items": _ITEM.findall(summary),
        })
    return items


def fetch(cik_to_ticker: dict[int, str] | None = None) -> list[dict]:
    user_agent = _require_user_agent()
    cik_to_ticker = cik_to_ticker if cik_to_ticker is not None else load_cik_to_ticker()
    items = []
    for form in config.SEC_FORMS:
        params = {"action": "getcurrent", "type": form, "owner": "include", "count": 100, "output": "atom"}
        xml = http_get(CURRENT_FEED, user_agent, params=params).text
        items.extend(parse_feed(xml, cik_to_ticker))
        time.sleep(0.2)  # la SEC consente al massimo 10 richieste al secondo
    return items
