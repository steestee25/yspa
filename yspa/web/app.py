"""Interfaccia web: feed delle notizie, segnalazioni, watchlist.

Avvio: uvicorn yspa.web.app:app --reload
"""
import base64
import secrets
from contextlib import contextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import config, db, export, pipeline, site
from . import render

app = FastAPI(title="YSPA")
app.mount("/static", StaticFiles(directory=render.STATIC), name="static")


@app.middleware("http")
async def password_check(request: Request, call_next):
    """Con YSPA_PASSWORD impostata, ogni pagina chiede la password (HTTP Basic). /health resta libera."""
    if not config.WEB_PASSWORD or request.url.path == "/health":
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            _, _, password = base64.b64decode(header[6:]).decode().partition(":")
        except Exception:
            password = ""
        if secrets.compare_digest(password.encode(), config.WEB_PASSWORD.encode()):
            return await call_next(request)
    return Response("Password richiesta", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Radar"'})


@contextmanager
def database():
    """Una connessione per richiesta: SQLite non permette di condividerla tra thread."""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


with database() as _conn:
    db.seed_watchlist(_conn)

@app.get("/", response_class=HTMLResponse)
def index():
    return site.render_page("server", base="/")


@app.get("/data.json")
def data():
    with database() as conn:
        return export.build_data(conn)


@app.get("/tickers.json")
def tickers():
    with database() as conn:
        return export.build_ticker_index(db.get_watchlist(conn))


@app.get("/health")
def health():
    """Stato delle fonti, per un controllo automatico (es. Docker healthcheck)."""
    with database() as conn:
        sources = db.get_source_status(conn)
        return {"last_fetch": db.last_fetch(conn), "sources": sources,
                "ok": bool(sources) and any(s["ok"] for s in sources)}


class NewTicker(BaseModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-]+$")
    name: str = Field(min_length=1, max_length=120)
    market: str = "US"
    aliases: str = ""


@app.post("/api/watchlist", status_code=201)
def add_ticker(item: NewTicker):
    aliases = [a.strip() for a in item.aliases.split("|") if a.strip()] or [item.name]
    with database() as conn:
        db.add_to_watchlist(conn, item.ticker.strip().upper(), item.name.strip(), aliases, item.market)
    return {"ok": True}


@app.delete("/api/watchlist/{ticker}")
def delete_ticker(ticker: str):
    with database() as conn:
        db.remove_from_watchlist(conn, ticker)
    return {"ok": True}


@app.post("/api/fetch")
def fetch_now():
    with database() as conn:
        pipeline.run_once(conn)
    return {"ok": True}
