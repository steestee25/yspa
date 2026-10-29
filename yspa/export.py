"""Dati della pagina in JSON: la pagina (statica o servita) li legge e li mostra."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, db
from .sources import sec_edgar
from .web import labels
from .web.timefmt import calm_title

SPARK_POINTS = 60
NEWS_LIMIT = 150
LOW_SCORE_DAYS = 2  # le notizie poco importanti restano nella pagina solo per pochi giorni


def _session_start(now: datetime) -> int:
    """Inizio della giornata di oggi (ora di Roma): il mini grafico mostra la giornata."""
    rome = now.astimezone(ZoneInfo(config.TIMEZONE))
    return int(rome.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def _downsample(points: list[tuple[int, float]], n: int) -> list[tuple[int, float]]:
    if len(points) <= n:
        return points
    step = len(points) / n
    picked = [points[int(i * step)] for i in range(n)]
    return picked[:-1] + [points[-1]]


def _news_item(n: dict) -> dict:
    return {
        "id": n["id"],
        "title": calm_title(n["title"]),
        "url": n["url"],
        "published_at": n["published_at"],
        "tickers": n["tickers"],
        "event": labels.event(n["event_type"]),
        "direction": n["direction"],
        "effect": labels.effect(n["direction"]),
        "score": n["score"],
        "importance": labels.importance(n["score"]),
        "reason": labels.reason(n["reason"]) if n["reason"] else "",
        "source": labels.source(n["source"]),
        "is_alert": bool(n["is_alert"]),
        "in_watchlist": bool(n["in_watchlist"]),
        "move": None if n.get("change_pct") is None else {
            "basis": n["price_basis"],
            "before": n["price_before"],
            "now": n["price_now"],
            "change_pct": n["change_pct"],
            "currency": n["currency"],
            "since": n["price_before_time"],
        },
    }


def build_data(conn, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    start = _session_start(now)
    recent = (now - timedelta(days=LOW_SCORE_DAYS)).isoformat(timespec="seconds")
    news = [n for n in db.list_news(conn, "all", limit=1000)
            if n["is_alert"] or n["score"] >= config.LOW_SCORE or n["published_at"] >= recent][:NEWS_LIMIT]
    by_ticker: dict[str, list[dict]] = {}
    for n in sorted(news, key=lambda x: x["published_at"], reverse=True):
        for t in n["tickers"]:
            by_ticker.setdefault(t, []).append(n)

    watchlist = []
    for w in db.get_watchlist(conn):
        last = db.latest_quote(conn, w["ticker"])
        history = db.quote_history(conn, w["ticker"], start)
        if not history and last:  # mercato chiuso oggi: si mostra l'ultima giornata disponibile
            day_start = _session_start(datetime.fromtimestamp(last["time"], timezone.utc))
            history = db.quote_history(conn, w["ticker"], day_start)
        spark = _downsample([(q["time"], q["price"]) for q in history], SPARK_POINTS)
        quote = None
        if last:
            change = round((last["price"] / last["prev_close"] - 1) * 100, 2) if last["prev_close"] else None
            quote = {"price": last["price"], "currency": last["currency"], "prev_close": last["prev_close"],
                     "change_pct": change, "time": last["time"], "source": last["source"]}
        items = by_ticker.get(w["ticker"], [])
        watchlist.append({
            "ticker": w["ticker"],
            "name": w["name"],
            "market": w["market"],
            "quote": quote,
            "spark": spark,
            "news": [_news_item(n) for n in items[:3]],
            "alerts": sum(1 for n in items if n["is_alert"]),
        })

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "last_fetch": db.last_fetch(conn),
        "every": config.RUN_EVERY_TEXT,
        "watchlist": watchlist,
        "news": [_news_item(n) for n in news],
        "sources": [{**s, "message": labels.source_error(s["detail"]) if not s["ok"] and s["detail"] else ""}
                    for s in db.get_source_status(conn)],
    }


def build_ticker_index(watchlist: list[dict]) -> list[list[str]]:
    """[ticker, nome, mercato] per la ricerca: società USA dalla SEC più i titoli già seguiti."""
    seen = set()
    rows = []
    for w in watchlist:
        rows.append([w["ticker"], w["name"], w["market"]])
        seen.add(w["ticker"])
    for ticker, name in sec_edgar.load_companies():
        if ticker not in seen:
            seen.add(ticker)
            rows.append([ticker, name, "US"])
    return rows
