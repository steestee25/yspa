"""Raccolta -> riconoscimento ticker -> classificazione -> salvataggio -> prezzi."""
import logging
from datetime import datetime

from . import config, db, prices
from .classify import classify, classify_sec_items
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
    found, _ = find_tickers(text, watchlist, title=raw["title"])
    tickers = list(dict.fromkeys(raw["tickers"] + found))
    # Per i depositi SEC il riassunto è solo l'elenco delle voci in inglese ("Entry into a Material
    # Definitive Agreement"): leggerlo come testo darebbe falsi positivi. Conta il codice della voce.
    if raw["source"].startswith("SEC"):
        result = classify_sec_items(raw.get("sec_items") or [])
    else:
        result = classify(text, raw.get("sec_items"))
    # I feed RSS contengono solo l'inizio del comunicato: se la notizia è importante ma il ticker
    # manca, lo cerchiamo nella pagina completa. Solo per queste, per non scaricare tutto.
    if not tickers and result.score >= config.ALERT_SCORE_WATCHLIST and raw["url"]:
        tickers, _ = find_tickers(page_reader(raw["url"]), watchlist, title=raw["title"])
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


def collect(conn, watchlist: list[dict]) -> list[dict]:
    """Legge tutte le fonti. Una fonte che non risponde non ferma le altre; lo stato finisce nel database."""
    fetchers = {
        "SEC EDGAR": sec_edgar.fetch,
        "GlobeNewswire": lambda: rss.fetch_one("globenewswire"),
        "PR Newswire": lambda: rss.fetch_one("prnewswire"),
    }
    if config.FINNHUB_API_KEY:
        fetchers["Finnhub"] = lambda: finnhub.fetch(watchlist)
    raw_items = []
    for name, fetch in fetchers.items():
        try:
            items = fetch()
        except Exception as exc:
            log.warning("Fonte %s non disponibile: %s", name, exc)
            db.set_source_status(conn, name, False, prices._short(exc))
            continue
        db.set_source_status(conn, name, True, items=len(items))
        raw_items.extend(items)
    return raw_items


def worth_keeping(item: dict) -> bool:
    if not item["source"].startswith("SEC"):
        return True
    return bool(item["in_watchlist"]) or item["score"] >= config.SEC_MIN_SCORE


def update_prices(conn, quotes_for=prices.best_quotes) -> int:
    """Aggiorna prezzo prima della notizia e prezzo attuale delle notizie che contano."""
    news = db.news_needing_prices(conn, config.PRICE_MIN_SCORE, config.PRICE_MAX_AGE_DAYS,
                                  config.PRICE_REFRESH_MINUTES)
    if not news:
        return 0
    oldest: dict[str, datetime] = {}
    for n in news:
        symbol, when = n["tickers"][0], datetime.fromisoformat(n["published_at"])
        oldest[symbol] = min(oldest.get(symbol, when), when)
    errors: dict[str, str] = {}
    quotes = quotes_for(oldest, errors)
    for source in ("Yahoo", "Nasdaq", "CNBC"):
        used = sum(1 for q in quotes.values() if q.source == source)
        if source in errors and not used:
            db.set_source_status(conn, f"Prezzi · {source}", False, errors[source])
        elif used or source not in errors:
            db.set_source_status(conn, f"Prezzi · {source}", True, items=used)
    updated = 0
    for n in news:
        quote = quotes.get(n["tickers"][0])
        move = prices.move_since(quote, n["published_at"], n) if quote else None
        db.set_prices(conn, n["id"], move)
        updated += bool(move)
    return updated


def run_once(conn) -> list[dict]:
    """Esegue un giro completo e restituisce le nuove segnalazioni."""
    watchlist = db.get_watchlist(conn)
    raw_items = collect(conn, watchlist)
    # Le notizie già salvate non si rianalizzano: niente pagine riscaricate a ogni giro.
    known = db.known_uids(conn, [r["uid"] for r in raw_items])
    new_alerts = []
    for raw in raw_items:
        if raw["uid"] in known:
            continue
        known.add(raw["uid"])
        item = enrich(raw, watchlist)
        if not worth_keeping(item):
            continue
        if db.insert_news(conn, item) and item["is_alert"]:
            new_alerts.append(item)
    db.purge_sec_noise(conn, config.SEC_MIN_SCORE)
    db.purge_old(conn, config.KEEP_DAYS, config.LOW_SCORE)
    try:
        update_prices(conn)
    except Exception as exc:  # i prezzi sono un di più: non devono fermare la raccolta
        log.exception("Aggiornamento prezzi fallito: %s", exc)
    return new_alerts
