"""Dati e filtri della pagina, condivisi tra server web e sito statico (GitHub Pages)."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import config, db
from . import labels
from .timefmt import calm_title, human_time, number, percent

TEMPLATES = Path(__file__).parent / "templates"

FILTERS = {
    "when": human_time,
    "calm": calm_title,
    "num": number,
    "pct": percent,
    "importance": labels.importance,
    "effect": labels.effect,
    "event": labels.event,
    "source": labels.source,
    "reason": labels.reason,
    "source_error": labels.source_error,
}

SORT_LABELS = {"importanza": "Prima le più importanti", "recenti": "Prima le più recenti"}


def page_context(conn, view: str, sort: str, tutte: int) -> dict:
    view = view if view in labels.VIEWS else "alerts"
    sort = sort if sort in SORT_LABELS else "importanza"
    # Nella vista "Tutte" le notizie poco importanti restano nascoste finché non le chiedi.
    min_score = config.LOW_SCORE if view == "all" and not tutte else 0
    news = [] if view == "watchlist" else db.list_news(conn, view, sort=sort, min_score=min_score)
    watchlist = db.get_watchlist(conn)
    return {
        "news": news,
        "hidden": db.count_below(conn, view, min_score) if min_score else 0,
        "near": db.near_alerts(conn) if view == "alerts" and not news else [],
        "watchlist": watchlist,
        "names": {w["ticker"]: w["name"] for w in watchlist},
        "last_fetch": db.last_fetch(conn),
        "sources": db.get_source_status(conn),
        "view": view,
        "views": labels.VIEWS,
        "sort": sort,
        "sorts": SORT_LABELS,
        "feedback_min_score": config.ALERT_SCORE_WATCHLIST,
        "static": False,
        "every_text": "ogni minuto",
    }


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    env.filters.update(FILTERS)
    return env
