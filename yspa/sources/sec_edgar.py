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

# Cosa significa ogni voce di un 8-K, in parole semplici. La 9.01 (allegati) non dice nulla e si omette.
ITEM_LABELS = {
    "1.01": "ha firmato un accordo importante",
    "1.02": "ha chiuso un accordo importante",
    "1.03": "è in fallimento o amministrazione controllata",
    "2.01": "ha completato un'acquisizione o una cessione",
    "2.02": "ha pubblicato i risultati finanziari",
    "2.03": "ha contratto nuovo debito",
    "2.05": "annuncia costi di ristrutturazione",
    "2.06": "annuncia svalutazioni",
    "3.01": "rischia l'esclusione dalla borsa",
    "3.02": "ha venduto nuove azioni fuori dal mercato",
    "3.03": "cambia i diritti degli azionisti",
    "4.01": "cambia revisore dei conti",
    "4.02": "dichiara non affidabili i bilanci passati",
    "5.01": "cambia chi controlla la società",
    "5.02": "cambia il management",
    "5.03": "modifica lo statuto",
    "5.07": "comunica i voti dell'assemblea",
    "7.01": "fa una comunicazione al mercato",
    "8.01": "comunica altri eventi",
}
FORM_LABELS = {
    "6-K": "comunicazione ufficiale di una società estera quotata negli USA",
    "SC 13D": "un investitore ha superato il 5% delle azioni",
}


def readable_title(form: str, company: str, items: list[str]) -> str:
    labels = [ITEM_LABELS[i] for i in items if i in ITEM_LABELS]
    if labels:
        return f"{company} {', '.join(labels)}"
    return f"{company}: {FORM_LABELS.get(form, 'documento ufficiale ' + form)}"


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
        sec_items = _ITEM.findall(summary) + (["SC 13D"] if match["form"] == "SC 13D" else [])
        ticker = cik_to_ticker.get(int(match["cik"]))
        items.append({
            "uid": f"sec:{entry.get('id', entry.get('link'))}:{match['cik']}",
            "source": f"SEC {match['form']}",
            "title": readable_title(match["form"], match["company"], sec_items),
            "summary": summary,
            "url": entry.get("link", ""),
            "published_at": struct_time_to_iso(entry.get("updated_parsed")),
            "tickers": [ticker] if ticker else [],
            "sec_items": sec_items,
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
