"""Sito statico per GitHub Pages: la pagina, i suoi dati (data.json) e l'elenco per la ricerca (tickers.json)."""
import csv
import json
import os
import shutil
from pathlib import Path

from . import db, export
from .web import render


def page_config(mode: str, base: str = "") -> dict:
    """mode "static" (GitHub Pages: modifiche via API di GitHub) o "server" (modifiche via /api)."""
    return {
        "mode": mode,
        "repo": os.environ.get("GITHUB_REPOSITORY", "steestee25/yspa"),
        "branch": os.environ.get("GITHUB_REF_NAME", "claude/wonderful-franklin-ay2r0p"),
        "data_url": f"{base}data.json",
        "tickers_url": f"{base}tickers.json",
        "api": f"{base}api",
    }


def render_page(mode: str, base: str = "") -> str:
    return render.environment().get_template("app.html").render(config=page_config(mode, base))


def build(conn, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    data = export.build_data(conn)
    files = {
        "index.html": render_page("static"),
        "data.json": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        "tickers.json": json.dumps(export.build_ticker_index(db.get_watchlist(conn)), ensure_ascii=False, separators=(",", ":")),
        ".nojekyll": "",
    }
    written = []
    for name, content in files.items():
        path = out / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    shutil.copytree(render.STATIC, out / "static", dirs_exist_ok=True)
    return written


def read_watchlist_csv(path: Path) -> list[tuple[str, str, list[str], str]]:
    """Righe: ticker,nome,mercato,altri nomi separati da |  (le righe che iniziano con # sono commenti)."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for row in csv.reader(line for line in f if line.strip() and not line.lstrip().startswith("#")):
            ticker, name, market, *rest = [c.strip() for c in row] + ["", "", ""]
            if not ticker or ticker.lower() == "ticker":
                continue
            aliases = [a.strip() for a in (rest[0] if rest else "").split("|") if a.strip()] or [name or ticker]
            rows.append((ticker.upper(), name or ticker, aliases, (market or "US").upper()))
    return rows


def sync_watchlist(conn, path: Path) -> int:
    """La watchlist diventa esattamente quella del file."""
    rows = read_watchlist_csv(path)
    wanted = {r[0] for r in rows}
    for w in db.get_watchlist(conn):
        if w["ticker"] not in wanted:
            db.remove_from_watchlist(conn, w["ticker"])
    for ticker, name, aliases, market in rows:
        db.add_to_watchlist(conn, ticker, name, aliases, market)
    return len(rows)
