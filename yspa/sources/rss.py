"""Comunicati stampa dai feed RSS gratuiti (GlobeNewswire, PR Newswire, BusinessWire...)."""
import logging

import feedparser

from .. import config
from .common import http_get, strip_html, struct_time_to_iso

log = logging.getLogger(__name__)


def parse_feed(name: str, xml: str) -> list[dict]:
    items = []
    for entry in feedparser.parse(xml).entries:
        link = entry.get("link", "")
        items.append({
            "uid": f"rss:{entry.get('id') or link}",
            "source": name,
            "title": strip_html(entry.get("title", "")),
            "summary": strip_html(entry.get("summary", "")),
            "url": link,
            "published_at": struct_time_to_iso(entry.get("published_parsed") or entry.get("updated_parsed")),
            "tickers": [],
            "sec_items": [],
        })
    return items


def fetch_one(name: str) -> list[dict]:
    response = http_get(config.RSS_FEEDS[name])
    items = parse_feed(name, response.text)
    # Alcuni siti rispondono 200 con una pagina di errore o un feed disattivato: non è un successo.
    if not items:
        raise RuntimeError(f"risposta senza notizie ({response.text[:80]!r})")
    return items


def fetch() -> list[dict]:
    items = []
    for name in config.RSS_FEEDS:
        try:
            items.extend(fetch_one(name))
        except Exception as exc:  # un feed fermo non deve bloccare gli altri
            log.warning("Feed %s non disponibile: %s", name, exc)
    return items
