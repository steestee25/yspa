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


def fetch() -> list[dict]:
    items = []
    for name, url in config.RSS_FEEDS.items():
        try:
            items.extend(parse_feed(name, http_get(url).text))
        except Exception as exc:  # un feed fermo non deve bloccare gli altri
            log.warning("Feed %s non disponibile: %s", name, exc)
    return items
