"""Finnhub (piano gratuito, 60 chiamate/minuto): notizie per ogni titolo USA della watchlist."""
from datetime import date, datetime, timedelta, timezone

from .. import config
from .common import http_get

URL = "https://finnhub.io/api/v1/company-news"


def parse_news(ticker: str, rows: list[dict]) -> list[dict]:
    return [{
        "uid": f"finnhub:{row['id']}",
        "source": f"Finnhub/{row.get('source', '')}",
        "title": row.get("headline", ""),
        "summary": row.get("summary", ""),
        "url": row.get("url", ""),
        "published_at": datetime.fromtimestamp(row["datetime"], timezone.utc).isoformat(timespec="seconds"),
        "tickers": [ticker],
        "sec_items": [],
    } for row in rows]


def fetch(watchlist: list[dict]) -> list[dict]:
    if not config.FINNHUB_API_KEY:
        return []
    today = date.today()
    items = []
    for w in watchlist:
        if w["market"] != "US":
            continue
        params = {"symbol": w["ticker"], "from": str(today - timedelta(days=2)), "to": str(today), "token": config.FINNHUB_API_KEY}
        items.extend(parse_news(w["ticker"], http_get(URL, params=params).json()))
    return items
