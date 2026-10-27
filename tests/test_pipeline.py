"""Test sui tre casi reali (testi ricostruiti dalle notizie, non scaricati)."""
from pathlib import Path

import pytest

from yspa import db, pipeline
from yspa.classify import classify
from yspa.sources import finnhub, rss, sec_edgar
from yspa.tickers import find_tickers

FIXTURES = Path(__file__).parent / "fixtures"
CIK_TO_TICKER = {1682852: "MRNA", 1999999: "BSP"}


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.seed_watchlist(c)
    return c


def by_title(items, fragment):
    return next(i for i in items if fragment in i["title"])


def test_sec_feed_maps_cik_to_ticker_and_items():
    items = sec_edgar.parse_feed((FIXTURES / "sec_current_6k.atom").read_text(), CIK_TO_TICKER)
    assert [i["tickers"] for i in items] == [["BSP"], ["MRNA"]]  # il "Filed by" del 13D è scartato
    assert by_title(items, "Moderna")["sec_items"] == ["7.01", "8.01", "9.01"]


def test_moderna_trial_success_is_top_alert(conn):
    raw = by_title(rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text()), "INTerpath")
    item = pipeline.enrich(raw, db.get_watchlist(conn))
    assert item["tickers"][:2] == ["MRNA", "MRK"]
    assert (item["event_type"], item["direction"], item["score"]) == ("studio clinico positivo", "su", 9)
    assert item["in_watchlist"] and item["is_alert"]


def test_bending_spoons_berkshire_is_alert(conn):
    raw = by_title(rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text()), "Berkshire")
    item = pipeline.enrich(raw, db.get_watchlist(conn))
    assert item["tickers"] == ["BSP"]
    assert item["event_type"] == "investimento strategico"
    assert item["is_alert"]


def test_discovery_needs_strong_event(conn):
    items = rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text())
    watchlist = db.get_watchlist(conn)
    boring = pipeline.enrich(by_title(items, "Annual Meeting"), watchlist)
    strong = pipeline.enrich(by_title(items, "Unknown Bio"), watchlist)
    assert not boring["is_alert"]
    assert strong["is_alert"] and not strong["in_watchlist"]


def test_store_is_idempotent_and_views(conn):
    watchlist = db.get_watchlist(conn)
    for raw in rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text()):
        assert db.insert_news(conn, pipeline.enrich(raw, watchlist))
        assert not db.insert_news(conn, pipeline.enrich(raw, watchlist))
    assert len(db.list_news(conn, "all")) == 4
    assert {n["tickers"][0] for n in db.list_news(conn, "discover")} == {"UNKB"}


def test_alias_matches_european_ticker(conn):
    tickers, in_wl = find_tickers("Rheinmetall wins EUR 2 billion order", db.get_watchlist(conn))
    assert tickers == ["RHM.DE"] and in_wl


def test_alias_does_not_match_inside_words(conn):
    tickers, _ = find_tickers("ASMLX fund update", db.get_watchlist(conn))
    assert tickers == []


@pytest.mark.parametrize("text, expected", [
    ("Company did not meet its primary endpoint", "studio clinico negativo"),
    ("Moderna stock joins the Nasdaq-100 replacing Warner Bros. Discovery", "ingresso in indice"),
    ("Moderna to replace Warner Bros. Discovery in the Nasdaq-100", "ingresso in indice"),
    ("SpaceX Reports Third Quarter 2026 Results", "risultati trimestrali"),
    ("Nike raises full-year guidance", "guidance alzata"),
    ("XYZ announces pricing of $500 million public offering", "aumento di capitale"),
])
def test_rules(text, expected):
    assert classify(text).event_type == expected


def test_finnhub_parse():
    rows = [{"id": 7, "datetime": 1760000000, "headline": "Nebius signs $3 billion contract", "summary": "", "url": "u", "source": "Reuters"}]
    item = finnhub.parse_news("NBIS", rows)[0]
    assert item["uid"] == "finnhub:7" and item["tickers"] == ["NBIS"]


def test_web_pages(tmp_path, monkeypatch):
    monkeypatch.setattr("yspa.config.DB_PATH", tmp_path / "web.db")
    from fastapi.testclient import TestClient
    import importlib
    import yspa.web.app as web
    importlib.reload(web)
    client = TestClient(web.app)
    assert "Bending Spoons" in client.get("/?view=watchlist").text
    client.post("/watchlist", data={"ticker": "pltr", "name": "Palantir", "market": "US"})
    assert any(w["ticker"] == "PLTR" for w in db.get_watchlist(web.conn))
    client.post("/watchlist/PLTR/delete")
    assert not any(w["ticker"] == "PLTR" for w in db.get_watchlist(web.conn))
    assert client.get("/api/news").json() == []
