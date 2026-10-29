"""Sito statico per GitHub Pages: le stesse pagine del server, solo da leggere."""
import csv
import os
from pathlib import Path

from . import db
from .web import render

PAGES = {  # vista -> file
    ("alerts", 0): "index.html",
    ("discover", 0): "nuovi.html",
    ("all", 0): "tutte.html",
    ("all", 1): "tutte-complete.html",
    ("watchlist", 0): "titoli.html",
}


def link(view: str, sort: str = "importanza", all_: int = 0) -> str:
    return PAGES.get((view, all_), PAGES.get((view, 0), "index.html"))


def build(conn, out: Path) -> list[Path]:
    repo = os.environ.get("GITHUB_REPOSITORY", "steestee25/yspa")
    branch = os.environ.get("GITHUB_REF_NAME", "claude/wonderful-franklin-ay2r0p")
    env = render.environment()
    template = env.get_template("index.html")
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for (view, all_), filename in PAGES.items():
        context = render.page_context(conn, view, "importanza", all_)
        context.update(
            static=True,
            link=link,
            every_text="ogni 5 minuti circa",
            run_url=f"https://github.com/{repo}/actions/workflows/pages.yml",
            watchlist_edit_url=f"https://github.com/{repo}/edit/{branch}/watchlist.csv",
        )
        path = out / filename
        path.write_text(template.render(**context), encoding="utf-8")
        written.append(path)
    (out / ".nojekyll").write_text("")
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
