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
    item = pipeline.enrich(raw, db.get_watchlist(conn), page_reader=lambda url: "")
    assert item["tickers"][:2] == ["MRNA", "MRK"]
    assert (item["event_type"], item["direction"], item["score"]) == ("studio clinico positivo", "su", 9)
    assert item["in_watchlist"] and item["is_alert"]


def test_bending_spoons_berkshire_is_alert(conn):
    raw = by_title(rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text()), "Berkshire")
    item = pipeline.enrich(raw, db.get_watchlist(conn), page_reader=lambda url: "")
    assert item["tickers"] == ["BSP"]
    assert item["event_type"] == "investimento strategico"
    assert item["is_alert"]


def test_discovery_needs_strong_event(conn):
    items = rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text())
    watchlist = db.get_watchlist(conn)
    boring = pipeline.enrich(by_title(items, "Annual Meeting"), watchlist, page_reader=lambda url: "")
    strong = pipeline.enrich(by_title(items, "Unknown Bio"), watchlist, page_reader=lambda url: "")
    assert not boring["is_alert"]
    assert strong["is_alert"] and not strong["in_watchlist"]


def test_store_is_idempotent_and_views(conn):
    watchlist = db.get_watchlist(conn)
    for raw in rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text()):
        assert db.insert_news(conn, pipeline.enrich(raw, watchlist, page_reader=lambda url: ""))
        assert not db.insert_news(conn, pipeline.enrich(raw, watchlist, page_reader=lambda url: ""))
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
    ("Oncolytics Biotech Reports Strong Durability and Survival Data in Anal Cancer", "dati clinici positivi"),
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
    conn = db.connect(tmp_path / "web.db")
    assert any(w["ticker"] == "PLTR" for w in db.get_watchlist(conn))
    client.post("/watchlist/PLTR/delete")
    assert not any(w["ticker"] == "PLTR" for w in db.get_watchlist(conn))
    assert client.get("/api/news").json() == []
    assert client.get("/health").json()["ok"] is False  # nessuna fonte controllata ancora
    for view in ("alerts", "discover", "all", "watchlist"):
        assert client.get(f"/?view={view}").status_code == 200


def test_ticker_from_full_page_when_feed_is_truncated(conn):
    raw = {"uid": "x", "source": "prnewswire", "url": "https://example.com/oncy", "tickers": [], "sec_items": [],
           "published_at": "2026-10-27T13:30:00+00:00",
           "title": "Oncolytics Biotech Reports Strong Durability and Survival Data in Anal Cancer",
           "summary": "CALGARY, Alberta, Oct. 27, 2026 -- Oncolytics Biotech, a leading company..."}
    page = "SAN DIEGO and CALGARY, Oct. 27, 2026 (GLOBE NEWSWIRE) -- Oncolytics Biotech® Inc. (NASDAQ: ONCY) today..."
    seen = []
    item = pipeline.enrich(raw, db.get_watchlist(conn), page_reader=lambda url: seen.append(url) or page)
    assert seen == ["https://example.com/oncy"]
    assert item["tickers"] == ["ONCY"] and item["is_alert"] == 0  # 7/10 fuori watchlist: sotto soglia scoperta


def test_unimportant_news_does_not_download_page(conn):
    raw = {"uid": "y", "source": "prnewswire", "url": "https://example.com/x", "tickers": [], "sec_items": [],
           "published_at": "2026-10-27T13:30:00+00:00", "title": "Company wins design award", "summary": ""}
    pipeline.enrich(raw, db.get_watchlist(conn), page_reader=lambda url: pytest.fail("non doveva scaricare"))


def test_human_time():
    from datetime import datetime, timezone
    from yspa.web.timefmt import human_time
    now = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)
    assert human_time("2026-10-27T14:15:00+00:00", now) == "oggi 15:15"   # Roma = UTC+1 dopo il 25 ottobre
    assert human_time("2026-10-26T17:02:00+00:00", now) == "ieri 18:02"
    assert human_time("2026-08-19T10:45:00+00:00", now) == "19 ago 12:45"  # ora legale: UTC+2
    assert human_time("2025-12-01T10:00:00+00:00", now) == "1 dic 2025"


def test_sort_by_importance_and_near_alerts(conn):
    watchlist = db.get_watchlist(conn)
    for raw in rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text()):
        db.insert_news(conn, pipeline.enrich(raw, watchlist, page_reader=lambda url: ""))
    by_score = [n["score"] for n in db.list_news(conn, "all")]
    assert by_score == sorted(by_score, reverse=True)
    recent = [n["published_at"] for n in db.list_news(conn, "all", sort="recenti")]
    assert recent == sorted(recent, reverse=True)
    assert all(not n["is_alert"] and n["score"] > 1 for n in db.near_alerts(conn))


def test_calm_title():
    from yspa.web.timefmt import calm_title
    assert calm_title("FINAL RESULTS OF THE OFFER: 89.42%") == "Final results of the offer: 89.42%"
    assert calm_title("NASDAQ Grants Rekor Systems Extension") == "NASDAQ Grants Rekor Systems Extension"


def sec_raw(form, items, company="Acme Corp", tickers=("ACME",)):
    return {"uid": f"sec:{form}{items}", "source": f"SEC {form}", "url": "", "tickers": list(tickers),
            "published_at": "2026-10-27T14:00:00+00:00",
            "title": sec_edgar.readable_title(form, company, items),
            "summary": "Item 1.01: Entry into a Material Definitive Agreement Item 9.01: Financial Statements",
            "sec_items": items}


def test_sec_material_agreement_is_not_a_takeover(conn):
    item = pipeline.enrich(sec_raw("8-K", ["1.01", "9.01"]), db.get_watchlist(conn), page_reader=lambda u: "")
    assert item["event_type"] == "accordo rilevante" and item["score"] == 6
    assert item["title"] == "Acme Corp ha firmato un accordo importante"


def test_sec_noise_is_dropped_unless_watchlist_or_strong(conn):
    wl = db.get_watchlist(conn)
    other = pipeline.enrich(sec_raw("8-K", ["8.01"]), wl, page_reader=lambda u: "")
    mine = pipeline.enrich(sec_raw("8-K", ["8.01"], "Moderna, Inc.", ["MRNA"]), wl, page_reader=lambda u: "")
    activist = pipeline.enrich(sec_raw("SC 13D", ["SC 13D"]), wl, page_reader=lambda u: "")
    assert not pipeline.worth_keeping(other)
    assert pipeline.worth_keeping(mine)
    assert pipeline.worth_keeping(activist) and activist["title"] == "Acme Corp: un investitore ha superato il 5% delle azioni"


def test_purge_removes_old_sec_noise(conn):
    wl = db.get_watchlist(conn)
    db.insert_news(conn, pipeline.enrich(sec_raw("8-K", ["8.01"]), wl, page_reader=lambda u: ""))
    db.purge_sec_noise(conn, 6)
    assert db.list_news(conn, "all") == []



def test_web_password(tmp_path, monkeypatch):
    monkeypatch.setattr("yspa.config.DB_PATH", tmp_path / "web.db")
    monkeypatch.setattr("yspa.config.WEB_PASSWORD", "segreta")
    from fastapi.testclient import TestClient
    import importlib
    import yspa.web.app as web
    importlib.reload(web)
    client = TestClient(web.app)
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("io", "sbagliata")).status_code == 401
    assert client.get("/", auth=("io", "segreta")).status_code == 200
    assert client.get("/health").status_code == 200


def test_exchange_suffixes_and_alias_only_in_title(conn):
    wl = db.get_watchlist(conn)
    text = "Acme (Euronext Paris: ACM) and Beta (TSX: BTA; NYSE American: BTA) sign deal. Body mentions Nike shoes."
    tickers, in_wl = find_tickers(text, wl, title="Acme and Beta sign deal")
    assert tickers == ["ACM.PA", "BTA.TO", "BTA"] and not in_wl
    assert find_tickers("Foot Locker results", wl, title="Foot Locker results")[0] == []
    assert find_tickers("x", wl, title="Nike raises guidance")[0] == ["NKE"]
    assert find_tickers("argenx (Euronext Brussels: ARGX) news", wl, title="x")[0] == ["ARGX.BR"]


def test_known_news_is_not_reanalysed(conn, monkeypatch):
    raw = rss.parse_feed("wire", (FIXTURES / "wire.rss").read_text())
    monkeypatch.setattr(pipeline, "collect", lambda c, w: raw)
    monkeypatch.setattr(pipeline, "update_prices", lambda c: 0)
    pages = []
    monkeypatch.setattr(pipeline, "tickers_from_page", lambda url: pages.append(url) or "")
    calls = []
    real_enrich = pipeline.enrich
    monkeypatch.setattr(pipeline, "enrich", lambda r, w: calls.append(r["uid"]) or real_enrich(r, w, page_reader=lambda u: ""))
    pipeline.run_once(conn)
    first = len(calls)
    pipeline.run_once(conn)
    assert first == 4 and len(calls) == 4
