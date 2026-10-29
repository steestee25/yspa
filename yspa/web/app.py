"""Interfaccia web: feed delle notizie, segnalazioni, watchlist.

Avvio: uvicorn yspa.web.app:app --reload
"""
import base64
import secrets
from contextlib import contextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .. import config, db, pipeline
from . import render

app = FastAPI(title="YSPA")
templates = Jinja2Templates(directory=render.TEMPLATES)
templates.env.filters.update(render.FILTERS)


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

def back_to(view: str, sort: str) -> RedirectResponse:
    return RedirectResponse("/?" + urlencode({"view": view, "sort": sort}), status_code=303)


@app.get("/")
def index(request: Request, view: str = "alerts", sort: str = "importanza", tutte: int = 0):
    with database() as conn:
        context = render.page_context(conn, view, sort, tutte)
    context["link"] = lambda v, srt, all_=0: "/?" + urlencode({"view": v, "sort": srt, **({"tutte": 1} if all_ else {})})
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/api/news")
def api_news(view: str = "alerts", sort: str = "importanza"):
    with database() as conn:
        return db.list_news(conn, view, sort=sort)


@app.get("/health")
def health():
    """Stato delle fonti, per un controllo automatico (es. Docker healthcheck)."""
    with database() as conn:
        sources = db.get_source_status(conn)
        return {"last_fetch": db.last_fetch(conn), "sources": sources,
                "ok": bool(sources) and any(s["ok"] for s in sources)}


@app.post("/fetch")
def fetch_now(view: str = Form("alerts"), sort: str = Form("importanza")):
    with database() as conn:
        pipeline.run_once(conn)
    return back_to(view, sort)


@app.post("/watchlist")
def add_ticker(ticker: str = Form(...), name: str = Form(...), aliases: str = Form(""), market: str = Form("US")):
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] or [name]
    with database() as conn:
        db.add_to_watchlist(conn, ticker.strip(), name.strip(), alias_list, market)
    return back_to("watchlist", "importanza")


@app.post("/watchlist/{ticker}/delete")
def delete_ticker(ticker: str):
    with database() as conn:
        db.remove_from_watchlist(conn, ticker)
    return back_to("watchlist", "importanza")


@app.post("/news/{news_id}/feedback")
def feedback(news_id: int, value: str = Form(...), view: str = Form("alerts"), sort: str = Form("importanza")):
    if value in ("interessa", "ignora"):
        with database() as conn:
            db.set_feedback(conn, news_id, value)
    return back_to(view, sort)
