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


def test_static_site_files(tmp_path):
    import json
    conn = db.connect(":memory:")
    db.seed_watchlist(conn)
    db.insert_news(conn, {"uid": "1", "source": "prnewswire", "title": "Moderna wins approval", "summary": "",
                          "url": "https://example.com/1", "published_at": "2026-10-29T14:00:00+00:00",
                          "tickers": ["MRNA"], "event_type": "approvazione farmaco", "direction": "su",
                          "score": 8, "reason": "frase: \"approval\"", "in_watchlist": 1, "is_alert": 1})
    files = {p.name: p for p in site.build(conn, tmp_path)}
    assert set(files) == {"index.html", "data.json", "tickers.json", ".nojekyll"}
    assert (tmp_path / "static/fonts/manrope-latin-wght-normal.woff2").stat().st_size > 10000
    page = files["index.html"].read_text()
    assert '"mode": "static"' in page and '"repo": "steestee25/yspa"' in page and "<form class=\"dlg\"" in page
    data = json.loads(files["data.json"].read_text())
    news = data["news"][0]
    assert news["title"] == "Moderna wins approval" and news["effect"] == "Può far salire il prezzo"
    assert news["importance"] == "Importanza alta (8 su 10)" and news["reason"] == "Nel testo compare «approval»."
    mrna = next(w for w in data["watchlist"] if w["ticker"] == "MRNA")
    assert mrna["alerts"] == 1 and mrna["news"][0]["id"] == news["id"] and mrna["quote"] is None
    index = json.loads(files["tickers.json"].read_text())
    assert ["MRNA", "Moderna", "US"] in index


def test_watchlist_written_by_the_page_is_read_back(tmp_path):
    # Righe come le scrive la pagina (prova in Playwright): nome con virgola tra virgolette, titolo europeo a mano.
    f = tmp_path / "watchlist.csv"
    f.write_text("ticker,nome,mercato,altri nomi\n"
                 'BRK-B,"Berkshire Hathaway Inc, Class B",US,Berkshire Hathaway\n'
                 "ENI.MI,ENI,EU,ENI\n")
    assert site.read_watchlist_csv(f) == [
        ("BRK-B", "Berkshire Hathaway Inc, Class B", ["Berkshire Hathaway"], "US"),
        ("ENI.MI", "ENI", ["ENI"], "EU"),
    ]
