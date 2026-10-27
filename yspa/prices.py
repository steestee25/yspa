"""Prezzi da Yahoo Finance (API dei grafici, gratuita e senza chiave, non ufficiale).

Per ogni notizia servono due numeri: il prezzo subito prima della notizia e quello attuale.
La differenza dice quanto il mercato ha già reagito.
"""
import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .sources.common import http_get

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo rifiuta le richieste senza un User-Agent da browser.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# Yahoo conserva le barre a 5 minuti solo per circa 60 giorni; oltre si usano quelle giornaliere.
INTRADAY_MAX_AGE = timedelta(days=55)
# Una barra giornaliera porta l'orario di apertura e dura quanto la seduta (USA: 6,5 ore).
DAILY_SESSION_SECONDS = int(6.5 * 3600)


@dataclass
class Chart:
    symbol: str
    currency: str
    times: list[int]     # secondi Unix, crescenti
    closes: list[float]
    last_price: float
    last_time: int
    bar_seconds: int = 300  # durata di una barra; per le giornaliere, la seduta (6,5 ore)

    def price_before(self, when: datetime) -> float | None:
        """Chiusura dell'ultima barra già conclusa all'istante dato: il prezzo senza la reazione."""
        i = bisect.bisect_right(self.times, int(when.timestamp()) - self.bar_seconds) - 1
        return self.closes[i] if i >= 0 else None


def parse_chart(data: dict, bar_seconds: int = 300) -> Chart | None:
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return None
    r = result[0]
    meta = r.get("meta", {})
    closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    # Le barre senza scambi hanno close = null: le scartiamo.
    pairs = [(t, c) for t, c in zip(r.get("timestamp") or [], closes) if c is not None]
    if not pairs and meta.get("regularMarketPrice") is None:
        return None
    times, values = (list(x) for x in zip(*pairs)) if pairs else ([], [])
    last_price = meta.get("regularMarketPrice")
    last_time = meta.get("regularMarketTime") or 0
    # Prima dell'apertura o dopo la chiusura l'ultima barra (pre/after-market) è più recente.
    if times and (last_price is None or times[-1] > last_time):
        last_price, last_time = values[-1], times[-1]
    return Chart(meta.get("symbol", ""), meta.get("currency", ""), times, values, last_price, last_time, bar_seconds)


def fetch_chart(symbol: str, since: datetime) -> Chart | None:
    now = datetime.now(timezone.utc)
    intraday = now - since < INTRADAY_MAX_AGE
    interval, bar_seconds = ("5m", 300) if intraday else ("1d", DAILY_SESSION_SECONDS)
    params = {
        "period1": int((since - timedelta(days=4)).timestamp()),  # margine per weekend e festivi
        "period2": int(now.timestamp()),
        "interval": interval,
        "includePrePost": "true",
    }
    return parse_chart(http_get(CHART_URL.format(symbol=symbol), USER_AGENT, params=params).json(), bar_seconds)


def move_since(chart: Chart, published_at: str) -> dict | None:
    """Prezzo prima della notizia, prezzo attuale e variazione percentuale."""
    before = chart.price_before(datetime.fromisoformat(published_at))
    if not before or chart.last_price is None:
        return None
    return {
        "price_before": round(before, 4),
        "price_now": round(chart.last_price, 4),
        "change_pct": round((chart.last_price / before - 1) * 100, 2),
        "currency": chart.currency,
        "price_time": datetime.fromtimestamp(chart.last_time, timezone.utc).isoformat(timespec="seconds"),
    }
