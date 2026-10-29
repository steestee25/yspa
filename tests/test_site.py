"""Sito statico per GitHub Pages e watchlist da file CSV."""
from yspa import db, site


def test_watchlist_csv_replaces_watchlist(tmp_path):
    conn = db.connect(":memory:")
    db.seed_watchlist(conn)
    csv_file = tmp_path / "watchlist.csv"
    csv_file.write_text("# commento\nticker,nome,mercato,altri nomi\nmrna,Moderna,US,Moderna|Moderna Inc\nLDO.MI,Leonardo,EU,\n\n")
    assert site.sync_watchlist(conn, csv_file) == 2
    wl = {w["ticker"]: w for w in db.get_watchlist(conn)}
    assert set(wl) == {"MRNA", "LDO.MI"}
    assert wl["MRNA"]["aliases"] == ["Moderna", "Moderna Inc"] and wl["LDO.MI"]["aliases"] == ["Leonardo"]
    assert wl["LDO.MI"]["market"] == "EU"


def test_repository_watchlist_file_is_valid():
    rows = site.read_watchlist_csv(__import__("pathlib").Path(__file__).parent.parent / "watchlist.csv")
    assert ("MRNA", "Moderna", ["Moderna"], "US") in rows and len(rows) >= 10


def test_static_site_has_pages_links_and_no_forms(tmp_path):
    conn = db.connect(":memory:")
    db.seed_watchlist(conn)
    db.insert_news(conn, {"uid": "1", "source": "prnewswire", "title": "Moderna wins approval", "summary": "",
                          "url": "https://example.com/1", "published_at": "2026-10-29T14:00:00+00:00",
                          "tickers": ["MRNA"], "event_type": "approvazione farmaco", "direction": "su",
                          "score": 8, "reason": "frase: \"approval\"", "in_watchlist": 1, "is_alert": 1})
    files = {p.name: p.read_text() for p in site.build(conn, tmp_path)}
    assert set(files) == {"index.html", "nuovi.html", "tutte.html", "tutte-complete.html", "titoli.html"}
    home = files["index.html"]
    assert "Moderna wins approval" in home and 'href="nuovi.html"' in home and 'href="titoli.html"' in home
    assert "<form" not in home and "Mi interessa" not in home
    assert 'http-equiv="refresh"' in home and "ogni 5 minuti circa" in home
    assert "watchlist.csv" in files["titoli.html"] and "<form" not in files["titoli.html"]
    assert (tmp_path / ".nojekyll").exists()
