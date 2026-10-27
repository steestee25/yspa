"""Impostazioni lette dalle variabili d'ambiente."""
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("YSPA_DB_PATH", "data/yspa.db"))

# La SEC rifiuta le richieste senza un User-Agent con nome ed email.
SEC_USER_AGENT = os.environ.get("YSPA_SEC_USER_AGENT", "")

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

# Moduli EDGAR da seguire: 8-K (aziende USA), 6-K (aziende estere quotate in USA, es. BSP),
# SC 13D (qualcuno supera il 5% con intenzioni attive).
SEC_FORMS = ["8-K", "6-K", "SC 13D"]

# Feed RSS gratuiti dei comunicati stampa (il feed generale di BusinessWire è stato disattivato). Modificabili senza toccare il codice sorgente.
RSS_FEEDS = {
    "globenewswire": "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/GlobeNewswire%20-%20News%20about%20Public%20Companies",
    "prnewswire": "https://www.prnewswire.com/rss/news-releases-list.rss",
}

# Soglie di punteggio (1-10) per le segnalazioni.
ALERT_SCORE_WATCHLIST = 5   # titolo in watchlist
ALERT_SCORE_DISCOVERY = 8   # titolo fuori watchlist: solo eventi forti

# Watchlist iniziale: ticker, nome, alias usati per riconoscerlo nel testo, mercato.
DEFAULT_WATCHLIST = [
    ("NKE", "Nike", ["Nike"], "US"),
    ("NBIS", "Nebius Group", ["Nebius"], "US"),
    ("APLD", "Applied Digital", ["Applied Digital"], "US"),
    ("MRNA", "Moderna", ["Moderna"], "US"),
    ("SPCX", "SpaceX", ["SpaceX"], "US"),
    ("BSP", "Bending Spoons", ["Bending Spoons"], "US"),
    ("ASML.AS", "ASML", ["ASML"], "EU"),
    ("ARGX.BR", "argenx", ["argenx"], "EU"),
    ("RHM.DE", "Rheinmetall", ["Rheinmetall"], "EU"),
    ("LDO.MI", "Leonardo", ["Leonardo S.p.A.", "Leonardo SpA"], "EU"),
    ("STMMI.MI", "STMicroelectronics", ["STMicroelectronics"], "EU"),
    ("NOVO-B.CO", "Novo Nordisk", ["Novo Nordisk"], "EU"),
]
