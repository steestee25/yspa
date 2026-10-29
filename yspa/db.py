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
CREATE TABLE IF NOT EXISTS quotes (
    ticker      TEXT NOT NULL,
    time        INTEGER NOT NULL,
    price       REAL NOT NULL,
    currency    TEXT NOT NULL DEFAULT '',
    prev_close  REAL,
    source      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (ticker, time)
);
CREATE TABLE IF NOT EXISTS source_status (
    name        TEXT PRIMARY KEY,
    ok          INTEGER NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    items       INTEGER NOT NULL DEFAULT 0,
    checked_at  TEXT NOT NULL,
    last_ok_at  TEXT
);
"""

# Colonne aggiunte dopo la prima versione: si aggiungono ai database già esistenti.
PRICE_COLUMNS = {
    "price_before": "REAL",
    "price_now": "REAL",
    "change_pct": "REAL",
    "currency": "TEXT",
    "price_time": "TEXT",
    "price_basis": "TEXT",       # "notizia" (prezzo prima della notizia) o "rilevamento" (prezzo al primo controllo)
    "price_before_time": "TEXT",
    "price_source": "TEXT",
    "price_checked_at": "TEXT",
    "day_change_pct": "REAL",    # variazione di oggi rispetto alla chiusura precedente
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Apre il database. Raccolta e pagina web sono processi diversi che scrivono sullo stesso file:
    WAL permette di leggere mentre l'altro scrive, busy_timeout aspetta invece di fallire subito."""
    path = path or config.DB_PATH
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
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


def known_uids(conn, uids: list[str]) -> set[str]:
    """Quali notizie sono già nel database: non serve rianalizzarle a ogni giro."""
    known: set[str] = set()
    for i in range(0, len(uids), 500):
        chunk = uids[i:i + 500]
        rows = conn.execute(f"SELECT uid FROM news WHERE uid IN ({','.join('?' * len(chunk))})", chunk)
        known.update(r["uid"] for r in rows)
    return known


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


VIEW_FILTERS = {
    "alerts": "is_alert = 1",
    "watchlist": "in_watchlist = 1",
    "discover": "is_alert = 1 AND in_watchlist = 0",
    "all": "1 = 1",
}


def list_news(conn, view: str = "all", limit: int = 200, sort: str = "importanza", min_score: int = 0) -> list[dict]:
    where = VIEW_FILTERS.get(view, VIEW_FILTERS["all"])
    order = SORTS.get(sort, SORTS["importanza"])
    rows = conn.execute(
        f"SELECT * FROM news WHERE {where} AND score >= ? ORDER BY {order} LIMIT ?", (min_score, limit)
    ).fetchall()
    return [{**dict(r), "tickers": json.loads(r["tickers"])} for r in rows]


def count_below(conn, view: str, min_score: int) -> int:
    where = VIEW_FILTERS.get(view, VIEW_FILTERS["all"])
    return conn.execute(f"SELECT COUNT(*) FROM news WHERE {where} AND score < ?", (min_score,)).fetchone()[0]


def purge_sec_noise(conn, min_score: int) -> None:
    """Toglie i depositi SEC poco importanti di titoli non seguiti (anche quelli salvati prima del filtro)."""
    conn.execute(
        "DELETE FROM news WHERE source LIKE 'SEC%' AND in_watchlist = 0 AND is_alert = 0 AND score < ? AND feedback IS NULL",
        (min_score,),
    )
    conn.commit()


def near_alerts(conn, limit: int = 5) -> list[dict]:
    """Le notizie non segnalate più importanti: da mostrare quando non ci sono segnalazioni."""
    rows = conn.execute(
        "SELECT * FROM news WHERE is_alert = 0 AND score > 1 ORDER BY score DESC, published_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [{**dict(r), "tickers": json.loads(r["tickers"])} for r in rows]


def last_fetch(conn) -> str | None:
    """Ora dell'ultimo giro di raccolta, anche se non ha trovato notizie nuove."""
    row = conn.execute("SELECT MAX(checked_at) FROM source_status").fetchone()[0]
    return row or conn.execute("SELECT MAX(fetched_at) FROM news").fetchone()[0]


def set_source_status(conn, name: str, ok: bool, detail: str = "", items: int = 0) -> None:
    now = now_iso()
    conn.execute(
        """INSERT INTO source_status (name, ok, detail, items, checked_at, last_ok_at)
           VALUES (:name, :ok, :detail, :items, :now, CASE WHEN :ok THEN :now END)
           ON CONFLICT(name) DO UPDATE SET ok = :ok, detail = :detail, items = :items, checked_at = :now,
               last_ok_at = CASE WHEN :ok THEN :now ELSE last_ok_at END""",
        {"name": name, "ok": int(ok), "detail": detail[:300], "items": items, "now": now},
    )
    conn.commit()


def get_source_status(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM source_status ORDER BY name")]


def purge_old(conn, keep_days: int, low_score: int) -> int:
    """Toglie le notizie poco importanti più vecchie di keep_days, tenendo segnalazioni e risposte."""
    since = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat(timespec="seconds")
    cur = conn.execute(
        "DELETE FROM news WHERE published_at < ? AND score < ? AND is_alert = 0 AND feedback IS NULL",
        (since, low_score),
    )
    conn.commit()
    return cur.rowcount


def news_needing_prices(conn, min_score: int, max_age_days: int, refresh_minutes: int) -> list[dict]:
    """Notizie da aggiornare: segnalazioni o titoli seguiti, recenti, non controllate da poco.

    Solo queste, per non chiedere centinaia di prezzi al minuto e farsi bloccare dalle fonti."""
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=max_age_days)).isoformat(timespec="seconds")
    stale = (now - timedelta(minutes=refresh_minutes)).isoformat(timespec="seconds")
    rows = conn.execute(
        """SELECT * FROM news WHERE tickers != '[]' AND (is_alert = 1 OR (in_watchlist = 1 AND score >= ?))
           AND published_at >= ? AND (price_checked_at IS NULL OR price_checked_at < ?)""",
        (min_score, since, stale),
    ).fetchall()
    return [{**dict(r), "tickers": json.loads(r["tickers"])} for r in rows]


def set_prices(conn, news_id: int, move: dict | None) -> None:
    """Salva i prezzi; con move=None segna solo che il controllo è avvenuto (fonte non disponibile)."""
    if move is None:
        conn.execute("UPDATE news SET price_checked_at = ? WHERE id = ?", (now_iso(), news_id))
    else:
        conn.execute(
            """UPDATE news SET price_before = :price_before, price_now = :price_now, change_pct = :change_pct,
                               currency = :currency, price_time = :price_time, price_basis = :price_basis,
                               price_source = :price_source, day_change_pct = :day_change_pct,
                               price_before_time = :price_before_time,
                               price_checked_at = :checked WHERE id = :id""",
            {"day_change_pct": None, "price_before_time": None, **move, "checked": now_iso(), "id": news_id},
        )
    conn.commit()


def set_feedback(conn, news_id: int, feedback: str) -> None:
    conn.execute("UPDATE news SET feedback = ? WHERE id = ?", (feedback, news_id))
    conn.commit()


def save_quote(conn, ticker: str, time: int, price: float, currency: str, prev_close: float | None, source: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO quotes (ticker, time, price, currency, prev_close, source) VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, time, price, currency, prev_close, source),
    )
    conn.commit()


def quote_history(conn, ticker: str, since: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM quotes WHERE ticker = ? AND time >= ? ORDER BY time", (ticker, since))
    return [dict(r) for r in rows]


def latest_quote(conn, ticker: str) -> dict | None:
    row = conn.execute("SELECT * FROM quotes WHERE ticker = ? ORDER BY time DESC LIMIT 1", (ticker,)).fetchone()
    return dict(row) if row else None


def purge_quotes(conn, before: int) -> None:
    conn.execute("DELETE FROM quotes WHERE time < ?", (before,))
    conn.commit()
