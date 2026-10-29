"""Riconoscimento dei ticker citati in una notizia.

I ticker si scrivono nel formato di Yahoo Finance: 'MRNA' per gli USA, 'RHM.DE' per Francoforte.
Così lo stesso simbolo identifica il titolo giusto anche quando si chiede il prezzo.
"""
import re

# Borsa citata nel comunicato -> suffisso del simbolo. "" = borsa USA.
EXCHANGE_SUFFIX = {
    "NASDAQ": "", "NYSE": "", "NYSE AMERICAN": "", "AMEX": "", "OTCQX": "", "OTCQB": "", "OTC": "",
    "TSX": ".TO", "TSXV": ".V", "TSX-V": ".V",
    "LSE": ".L", "AIM": ".L",
    "XETRA": ".DE", "FRANKFURT": ".F", "FSE": ".F",
    "SIX": ".SW",
    "EURONEXT PARIS": ".PA", "EURONEXT AMSTERDAM": ".AS", "EURONEXT BRUSSELS": ".BR",
    "EURONEXT LISBON": ".LS", "EURONEXT DUBLIN": ".IR", "EURONEXT OSLO": ".OL", "OSLO": ".OL",
    "EURONEXT MILAN": ".MI", "BORSA ITALIANA": ".MI",
    "NASDAQ STOCKHOLM": ".ST", "NASDAQ COPENHAGEN": ".CO", "NASDAQ HELSINKI": ".HE",
}

_EXCHANGES = sorted(EXCHANGE_SUFFIX, key=len, reverse=True)  # i nomi lunghi prima: "NYSE American" prima di "NYSE"
_EXCHANGE = "|".join(re.escape(e).replace(r"\ ", r"\s+") for e in _EXCHANGES)
_SYMBOL = r"[A-Z][A-Z0-9.\-]{0,9}"
# "(NASDAQ: MRNA)", "(NYSE: NKE)", "(Euronext Brussels: ARGX; NASDAQ: ARGX)", "(TSX: ABC) (NYSE American: ABC)"
EXCHANGE_TAG = re.compile(rf"\b({_EXCHANGE})\s*:\s*({_SYMBOL})\b", re.IGNORECASE)
_PAREN = re.compile(r"\(([^()]{3,120})\)")


def find_tickers(text: str, watchlist: list[dict], title: str | None = None) -> tuple[list[str], bool]:
    """Restituisce i ticker trovati (formato Yahoo) e se almeno uno è in watchlist.

    I tag di borsa si cercano in tutto il testo, ma solo dentro parentesi, come nei comunicati.
    Gli alias della watchlist (es. "Nike") si cercano solo nel titolo: nel corpo un nome compare
    spesso per altri motivi (un negozio che vende Nike non è una notizia su Nike).
    """
    found: list[str] = []
    for paren in _PAREN.finditer(text):
        for exchange, symbol in EXCHANGE_TAG.findall(paren.group(1)):
            suffix = EXCHANGE_SUFFIX[" ".join(exchange.upper().split())]
            ticker = symbol.upper() + suffix
            if ticker not in found:
                found.append(ticker)

    watch = {w["ticker"]: w for w in watchlist}
    title = text if title is None else title
    for w in watchlist:
        if w["ticker"] in found:
            continue
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", title, re.IGNORECASE) for alias in w["aliases"]):
            found.append(w["ticker"])

    return found, any(t in watch for t in found)
