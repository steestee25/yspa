"""Database SQLite: watchlist e notizie."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    ticker   TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    aliases  TEXT NOT NULL DEFAULT '[]',
    market   TEXT NOT NULL DEFAULT 'US',
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    uid           TEXT NOT NULL UNIQUE,
    source        TEXT NOT NULL,
    title         TEXT NOT NULL,
    summary       TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    published_at  TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    tickers       TEXT NOT NULL DEFAULT '[]',
    event_type    TEXT NOT NULL DEFAULT 'altro',
    direction     TEXT NOT NULL DEFAULT 'neutra',
    score         INTEGER NOT NULL DEFAULT 0,
    reason        TEXT NOT NULL DEFAULT '',
    in_watchlist  INTEGER NOT NULL DEFAULT 0,
    is_alert      INTEGER NOT NULL DEFAULT 0,
    feedback      TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at DESC);
"""

# Colonne aggiunte dopo la prima versione: si aggiungono ai database già esistenti.
PRICE_COLUMNS = {
    "price_before": "REAL",
    "price_now": "REAL",
    "change_pct": "REAL",
    "currency": "TEXT",
    "price_time": "TEXT",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(news)")}
    for column, kind in PRICE_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE news ADD COLUMN {column} {kind}")
    conn.commit()
    return conn


def seed_watchlist(conn: sqlite3.Connection) -> None:
    """Inserisce la watchlist iniziale solo se la tabella è vuota."""
    if conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]:
        return
    for ticker, name, aliases, market in config.DEFAULT_WATCHLIST:
        add_to_watchlist(conn, ticker, name, aliases, market)


def add_to_watchlist(conn, ticker: str, name: str, aliases: list[str], market: str = "US") -> None:
    conn.execute(
        "INSERT OR REPLACE INTO watchlist (ticker, name, aliases, market, added_at) VALUES (?, ?, ?, ?, ?)",
        (ticker.upper(), name, json.dumps(aliases), market, now_iso()),
    )
    conn.commit()


def remove_from_watchlist(conn, ticker: str) -> None:
    conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
    conn.commit()


def get_watchlist(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM watchlist ORDER BY ticker").fetchall()
    return [{**dict(r), "aliases": json.loads(r["aliases"])} for r in rows]


def insert_news(conn, item: dict) -> bool:
    """Salva una notizia. Restituisce False se era già presente."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO news
           (uid, source, title, summary, url, published_at, fetched_at, tickers,
            event_type, direction, score, reason, in_watchlist, is_alert)
           VALUES (:uid, :source, :title, :summary, :url, :published_at, :fetched_at, :tickers,
                   :event_type, :direction, :score, :reason, :in_watchlist, :is_alert)""",
        {**item, "tickers": json.dumps(item["tickers"]), "fetched_at": now_iso()},
    )
    conn.commit()
    return cur.rowcount == 1


SORTS = {
    "importanza": "score DESC, published_at DESC",
    "recenti": "published_at DESC",
}


def list_news(conn, view: str = "all", limit: int = 200, sort: str = "importanza") -> list[dict]:
    where = {
        "alerts": "WHERE is_alert = 1",
        "watchlist": "WHERE in_watchlist = 1",
        "discover": "WHERE is_alert = 1 AND in_watchlist = 0",
    }.get(view, "")
    order = SORTS.get(sort, SORTS["importanza"])
    rows = conn.execute(f"SELECT * FROM news {where} ORDER BY {order} LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "tickers": json.loads(r["tickers"])} for r in rows]


def near_alerts(conn, limit: int = 5) -> list[dict]:
    """Le notizie non segnalate più importanti: da mostrare quando non ci sono segnalazioni."""
    rows = conn.execute(
        "SELECT * FROM news WHERE is_alert = 0 AND score > 1 ORDER BY score DESC, published_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [{**dict(r), "tickers": json.loads(r["tickers"])} for r in rows]


def last_fetch(conn) -> str | None:
    return conn.execute("SELECT MAX(fetched_at) FROM news").fetchone()[0]


def news_needing_prices(conn, min_score: int, max_age_days: int) -> list[dict]:
    """Notizie con ticker abbastanza importanti e recenti da meritare il prezzo aggiornato."""
    since = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT * FROM news WHERE tickers != '[]' AND (score >= ? OR is_alert = 1) AND published_at >= ?",
        (min_score, since),
    ).fetchall()
    return [{**dict(r), "tickers": json.loads(r["tickers"])} for r in rows]


def set_prices(conn, news_id: int, move: dict) -> None:
    conn.execute(
        """UPDATE news SET price_before = :price_before, price_now = :price_now, change_pct = :change_pct,
                           currency = :currency, price_time = :price_time WHERE id = :id""",
        {**move, "id": news_id},
    )
    conn.commit()


def set_feedback(conn, news_id: int, feedback: str) -> None:
    conn.execute("UPDATE news SET feedback = ? WHERE id = ?", (feedback, news_id))
    conn.commit()
