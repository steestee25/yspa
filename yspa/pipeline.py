"""Raccolta -> riconoscimento ticker -> classificazione -> salvataggio."""
import logging

from . import config, db
from .classify import classify
from .sources import finnhub, rss, sec_edgar
from .sources.common import http_get, strip_html
from .tickers import find_tickers

log = logging.getLogger(__name__)

# Il ticker sta nel primo paragrafo del comunicato, subito dopo la riga con città e data.
DATELINE_MARKERS = ("/PRNewswire/", "(GLOBE NEWSWIRE)", "/CNW/", "(BUSINESS WIRE)")
DATELINE_WINDOW = 3000


def tickers_from_page(url: str) -> str:
    """Testo del primo paragrafo del comunicato completo, o '' se non lo si trova."""
    try:
        text = strip_html(http_get(url).text)
    except Exception as exc:
        log.warning("Pagina %s non leggibile: %s", url, exc)
        return ""
    for marker in DATELINE_MARKERS:
        start = text.find(marker)
        if start != -1:
            return text[start:start + DATELINE_WINDOW]
    return ""


def enrich(raw: dict, watchlist: list[dict], page_reader=tickers_from_page) -> dict:
    text = f"{raw['title']}. {raw['summary']}"
    found, _ = find_tickers(text, watchlist)
    tickers = list(dict.fromkeys(raw["tickers"] + found))
    result = classify(text, raw.get("sec_items"))
    # I feed RSS contengono solo l'inizio del comunicato: se la notizia è importante ma il ticker
    # manca, lo cerchiamo nella pagina completa. Solo per queste, per non scaricare tutto.
    if not tickers and result.score >= config.ALERT_SCORE_WATCHLIST and raw["url"]:
        tickers, _ = find_tickers(page_reader(raw["url"]), watchlist)
    in_watchlist = bool(set(tickers) & {w["ticker"] for w in watchlist})
    threshold = config.ALERT_SCORE_WATCHLIST if in_watchlist else config.ALERT_SCORE_DISCOVERY
    return {
        **{k: raw[k] for k in ("uid", "source", "title", "summary", "url", "published_at")},
        "tickers": tickers,
        "event_type": result.event_type,
        "direction": result.direction,
        "score": result.score,
        "reason": result.reason,
        "in_watchlist": int(in_watchlist),
        # Senza ticker non si sa su cosa operare: non è una segnalazione.
        "is_alert": int(bool(tickers) and result.score >= threshold),
    }


def collect(watchlist: list[dict]) -> list[dict]:
    fetchers = {
        "SEC EDGAR": sec_edgar.fetch,
        "RSS": rss.fetch,
        "Finnhub": lambda: finnhub.fetch(watchlist),
    }
    raw_items = []
    for name, fetch in fetchers.items():
        try:
            raw_items.extend(fetch())
        except Exception as exc:  # una fonte che non risponde non deve fermare le altre
            log.warning("Fonte %s non disponibile: %s", name, exc)
    return raw_items


def run_once(conn) -> list[dict]:
    """Esegue un giro completo e restituisce le nuove segnalazioni."""
    watchlist = db.get_watchlist(conn)
    new_alerts = []
    for raw in collect(watchlist):
        item = enrich(raw, watchlist)
        if db.insert_news(conn, item) and item["is_alert"]:
            new_alerts.append(item)
    return new_alerts
