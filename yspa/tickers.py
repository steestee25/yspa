"""Riconoscimento dei ticker citati in una notizia."""
import re

# Formato tipico dei comunicati: "(NASDAQ: MRNA)", "(NYSE: NKE)", "(Euronext Brussels: ARGX)".
EXCHANGE_TAG = re.compile(
    r"\((?:NASDAQ|Nasdaq|NYSE(?: American)?|AMEX|OTCQX|OTCQB|TSX|LSE|XETRA|Xetra|SIX|"
    r"Euronext(?: [A-Z][a-z]+)?|Borsa Italiana|Euronext Milan)\s*:\s*([A-Z][A-Z0-9.\-]{0,9})"
    r"(?:\s*[;,]\s*(?:NASDAQ|NYSE|Euronext(?: [A-Z][a-z]+)?)\s*:\s*([A-Z][A-Z0-9.\-]{0,9}))?\)"
)


def base_symbol(ticker: str) -> str:
    """'ASML.AS' -> 'ASML', 'NOVO-B.CO' -> 'NOVO-B'."""
    return ticker.split(".")[0].upper()


def find_tickers(text: str, watchlist: list[dict]) -> tuple[list[str], bool]:
    """Restituisce i ticker trovati e se almeno uno è in watchlist.

    I ticker della watchlist sono restituiti nella forma della watchlist (es. 'ASML.AS').
    """
    found: list[str] = []
    for match in EXCHANGE_TAG.finditer(text):
        for symbol in match.groups():
            if symbol and symbol not in found:
                found.append(symbol)

    by_base = {base_symbol(w["ticker"]): w["ticker"] for w in watchlist}
    result = [by_base.get(sym, sym) for sym in found]

    for w in watchlist:
        if w["ticker"] in result:
            continue
        for alias in w["aliases"]:
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text, re.IGNORECASE):
                result.append(w["ticker"])
                break

    watch_set = {w["ticker"] for w in watchlist}
    return result, any(t in watch_set for t in result)
