"""Prezzi da fonti gratuite, in catena: Yahoo Finance -> Nasdaq -> CNBC.

Per ogni notizia servono due numeri: il prezzo subito prima della notizia e quello attuale.
- Yahoo dà lo storico (barre a 5 minuti o giornaliere) per USA ed Europa, ma blocca spesso i server cloud.
- Nasdaq dà le barre al minuto di oggi (pre-market compreso), solo per i titoli USA.
- CNBC dà l'ultimo prezzo e la chiusura di ieri per USA ed Europa, senza storico.
Se nessuna fonte ha le barre del momento della notizia, il prezzo "prima" è quello del primo
controllo del radar, e la pagina lo dice ("da quando il radar l'ha vista").
"""
import bisect
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from .sources.common import BROWSER_UA, http_get

log = logging.getLogger(__name__)

# Le fonti di prezzo rifiutano le richieste senza un User-Agent da browser.
USER_AGENT = BROWSER_UA
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/chart"
CNBC_URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
CNBC_BATCH = 25

# Yahoo conserva le barre a 5 minuti solo per circa 60 giorni; oltre si usano quelle giornaliere.
INTRADAY_MAX_AGE = timedelta(days=55)
# Una barra giornaliera porta l'orario di apertura e dura quanto la seduta (USA: 6,5 ore).
DAILY_SESSION_SECONDS = int(6.5 * 3600)
# Una fonte che risponde 429 o 403 viene lasciata in pace per questo tempo.
BLOCK_SECONDS = 15 * 60

# Suffisso Yahoo -> suffisso CNBC (verificati: DE, NL, BE, IT).
CNBC_SUFFIX = {
    ".DE": "-DE", ".F": "-DE", ".AS": "-NL", ".BR": "-BE", ".PA": "-FR", ".MI": "-IT", ".LS": "-PT",
    ".IR": "-IE", ".L": "-GB", ".SW": "-CH", ".MC": "-ES", ".CO": "-DK", ".ST": "-SE", ".HE": "-FI",
    ".OL": "-NO", ".TO": "-CA", ".V": "-CA",
}


class SourceBlocked(Exception):
    """La fonte ha rifiutato la richiesta (429/403): inutile riprovare subito."""


_blocked_until: dict[str, float] = {}


def is_blocked(source: str) -> bool:
    return _blocked_until.get(source, 0) > time.time()


def _get_json(source: str, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    if is_blocked(source):
        raise SourceBlocked(f"{source} in pausa dopo un rifiuto")
    try:
        return http_get(url, USER_AGENT, params=params, headers=headers).json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 429):
            _blocked_until[source] = time.time() + BLOCK_SECONDS
            raise SourceBlocked(f"{source} ha rifiutato ({exc.response.status_code})") from exc
        raise


def is_us(symbol: str) -> bool:
    return "." not in symbol


@dataclass
class Quote:
    symbol: str
    source: str
    last: float | None
    last_time: int               # secondi Unix
    currency: str = ""
    prev_close: float | None = None
    times: list[int] = field(default_factory=list)    # inizio di ogni barra, crescente
    closes: list[float] = field(default_factory=list)
    bar_seconds: int = 300

    def price_before(self, when: datetime) -> float | None:
        """Chiusura dell'ultima barra già conclusa all'istante dato: il prezzo senza la reazione.

        None se le barre non coprono quell'istante (notizia precedente alla prima barra)."""
        if not self.times or int(when.timestamp()) < self.times[0] + self.bar_seconds:
            return None
        i = bisect.bisect_right(self.times, int(when.timestamp()) - self.bar_seconds) - 1
        return self.closes[i] if i >= 0 else None

    @property
    def day_change_pct(self) -> float | None:
        if self.last is None or not self.prev_close:
            return None
        return round((self.last / self.prev_close - 1) * 100, 2)


# Compatibilità con i test e il comando "price": un grafico è una Quote con barre.
Chart = Quote


def _to_float(value) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


# --- Yahoo -------------------------------------------------------------------------------------

def parse_chart(data: dict, bar_seconds: int = 300) -> Quote | None:
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
    prev = meta.get("previousClose") or meta.get("chartPreviousClose")
    return Quote(meta.get("symbol", ""), "Yahoo", last_price, last_time, meta.get("currency", ""),
                 prev, times, values, bar_seconds)


def yahoo_chart(symbol: str, since: datetime) -> Quote | None:
    now = datetime.now(timezone.utc)
    intraday = now - since < INTRADAY_MAX_AGE
    interval, bar_seconds = ("5m", 300) if intraday else ("1d", DAILY_SESSION_SECONDS)
    params = {
        "period1": int((since - timedelta(days=4)).timestamp()),  # margine per weekend e festivi
        "period2": int(now.timestamp()),
        "interval": interval,
        "includePrePost": "true",
    }
    return parse_chart(_get_json("Yahoo", YAHOO_URL.format(symbol=symbol), params), bar_seconds)


fetch_chart = yahoo_chart


# --- Nasdaq ------------------------------------------------------------------------------------

NEW_YORK = ZoneInfo("America/New_York")


def _nasdaq_time(x_ms: int) -> int:
    """Nasdaq scrive l'ora di New York come se fosse UTC ("4:00 AM ET" -> 04:00Z): la riportiamo all'istante vero."""
    wall = datetime.fromtimestamp(x_ms / 1000, timezone.utc).replace(tzinfo=None)
    return int(wall.replace(tzinfo=NEW_YORK).timestamp())


def parse_nasdaq(symbol: str, data: dict) -> Quote | None:
    d = data.get("data") or {}
    bars = [(_nasdaq_time(b["x"]), float(b["y"])) for b in d.get("chart") or [] if b.get("y") is not None]
    last = _to_float(d.get("lastSalePrice"))
    if last is None and not bars:
        return None
    times, closes = (list(x) for x in zip(*bars)) if bars else ([], [])
    last_time = times[-1] if times else int(time.time())
    if last is None:
        last = closes[-1]
    return Quote(symbol, "Nasdaq", last, last_time, "USD", _to_float(d.get("previousClose")), times, closes, 60)


def nasdaq_chart(symbol: str) -> Quote | None:
    data = _get_json("Nasdaq", NASDAQ_URL.format(symbol=symbol), {"assetclass": "stocks"},
                     {"Accept": "application/json"})
    return parse_nasdaq(symbol, data)


# --- CNBC --------------------------------------------------------------------------------------

def to_cnbc(symbol: str) -> str | None:
    if is_us(symbol):
        return symbol
    base, _, suffix = symbol.rpartition(".")
    cnbc = CNBC_SUFFIX.get("." + suffix)
    return f"{base.replace('-', '')}{cnbc}" if cnbc else None


def parse_cnbc(data: dict, wanted: dict[str, str]) -> dict[str, Quote]:
    """wanted: simbolo CNBC -> simbolo nostro."""
    quotes = ((data.get("FormattedQuoteResult") or {}).get("FormattedQuote")) or []
    if isinstance(quotes, dict):
        quotes = [quotes]
    out = {}
    for q in quotes:
        ours = wanted.get(q.get("symbol"))
        last = _to_float(q.get("last"))
        if ours is None or str(q.get("code")) != "0" or last is None:
            continue
        ts = q.get("last_time")
        try:
            last_time = int(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()) if ts else int(time.time())
        except ValueError:
            last_time = int(time.time())
        # Fuori seduta CNBC riporta a parte il pre/after-market, più recente.
        ext = q.get("ExtendedMktQuote") or {}
        ext_last = _to_float(ext.get("last"))
        if ext_last is not None and ext.get("last_time"):
            try:
                ext_time = int(datetime.strptime(ext["last_time"], "%Y-%m-%dT%H:%M:%S.%f%z").timestamp())
                if ext_time > last_time:
                    last, last_time = ext_last, ext_time
            except ValueError:
                pass
        out[ours] = Quote(ours, "CNBC", last, last_time, q.get("currencyCode") or "",
                          _to_float(q.get("previous_day_closing")))
    return out


def cnbc_quotes(symbols: list[str]) -> dict[str, Quote]:
    wanted = {c: s for s in symbols if (c := to_cnbc(s))}
    out: dict[str, Quote] = {}
    names = list(wanted)
    for i in range(0, len(names), CNBC_BATCH):
        params = {"symbols": "|".join(names[i:i + CNBC_BATCH]), "requestMethod": "itv", "noform": "1",
                  "partnerId": "2", "fund": "1", "exthrs": "1", "output": "json", "events": "1"}
        out.update(parse_cnbc(_get_json("CNBC", CNBC_URL, params), wanted))
    return out


# --- Catena ------------------------------------------------------------------------------------

def best_quotes(requests: dict[str, datetime], errors: dict[str, str] | None = None) -> dict[str, Quote]:
    """Per ogni simbolo (con l'istante della notizia più vecchia) la quotazione migliore disponibile.

    Prima le fonti con barre (servono per il prezzo prima della notizia), poi CNBC per il resto."""
    errors = errors if errors is not None else {}
    out: dict[str, Quote] = {}
    for symbol, since in requests.items():
        for name, fetch in (("Yahoo", lambda: yahoo_chart(symbol, since)),
                            ("Nasdaq", lambda: nasdaq_chart(symbol) if is_us(symbol) else None)):
            try:
                quote = fetch()
            except Exception as exc:
                errors[name] = _short(exc)
                continue
            if quote and quote.last is not None:
                out[symbol] = quote
                break
    missing = [s for s in requests if s not in out]
    if missing:
        try:
            out.update(cnbc_quotes(missing))
        except Exception as exc:
            errors["CNBC"] = _short(exc)
    return out


def watchlist_quotes(symbols: list[str], errors: dict[str, str] | None = None) -> dict[str, Quote]:
    """Quotazioni dei titoli seguiti, per le schede della pagina.

    CNBC per tutti in una sola richiesta (USA ed Europa); per i titoli USA anche Nasdaq, che aggiunge
    le barre al minuto di oggi per il mini grafico e ha la precedenza quando risponde."""
    errors = errors if errors is not None else {}
    out: dict[str, Quote] = {}
    try:
        out.update(cnbc_quotes(symbols))
    except Exception as exc:
        errors["CNBC"] = _short(exc)
    for symbol in symbols:
        if not is_us(symbol):
            continue
        try:
            quote = nasdaq_chart(symbol)
        except Exception as exc:
            errors["Nasdaq"] = _short(exc)
            continue
        if quote and quote.last is not None:
            if quote.prev_close is None and symbol in out:
                quote.prev_close = out[symbol].prev_close
            out[symbol] = quote
    return out


def _short(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc).splitlines()[0][:160]}"


def move_since(quote: Quote, published_at: str, previous: dict | None = None) -> dict | None:
    """Prezzo prima della notizia, prezzo attuale e variazione.

    previous: i prezzi già salvati per quella notizia, per non perdere il prezzo "prima"."""
    if quote.last is None:
        return None
    previous = previous or {}
    when = datetime.fromisoformat(published_at)
    before, basis, before_time = quote.price_before(when), "notizia", published_at
    if before is None and previous.get("price_basis") == "notizia":
        before, basis, before_time = previous["price_before"], "notizia", previous.get("price_before_time")
    if before is None and quote.prev_close and _published_after_previous_close(quote, when):
        before, basis, before_time = quote.prev_close, "notizia", published_at
    if before is None and previous.get("price_before"):
        before, basis, before_time = previous["price_before"], previous.get("price_basis") or "rilevamento", previous.get("price_before_time")
    if before is None:
        before, basis = quote.last, "rilevamento"
        before_time = datetime.fromtimestamp(quote.last_time, timezone.utc).isoformat(timespec="seconds")
    return {
        "price_before": round(before, 4),
        "price_now": round(quote.last, 4),
        "change_pct": round((quote.last / before - 1) * 100, 2) if before else None,
        "currency": quote.currency,
        "price_time": datetime.fromtimestamp(quote.last_time, timezone.utc).isoformat(timespec="seconds"),
        "price_basis": basis,
        "price_before_time": before_time,
        "price_source": quote.source,
        "day_change_pct": quote.day_change_pct,
    }


def _published_after_previous_close(quote: Quote, when: datetime) -> bool:
    """Notizia uscita dopo la chiusura della seduta precedente e prima delle barre di oggi.

    In quel caso il prezzo "prima della notizia" è la chiusura precedente. Vale solo per i titoli USA
    con le barre di oggi (Nasdaq): la chiusura è alle 16:00 di New York dell'ultimo giorno feriale."""
    if not quote.times or quote.source != "Nasdaq":
        return False
    first_day = datetime.fromtimestamp(quote.times[0], NEW_YORK).date()
    day = first_day - timedelta(days=1)
    while day.weekday() >= 5:  # sabato e domenica: si torna al venerdì
        day -= timedelta(days=1)
    previous_close = datetime(day.year, day.month, day.day, 16, 0, tzinfo=NEW_YORK)
    return previous_close <= when < datetime.fromtimestamp(quote.times[0], timezone.utc)
