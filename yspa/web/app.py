"""Interfaccia web: feed delle notizie, segnalazioni, watchlist.

Avvio: uvicorn yspa.web.app:app --reload
"""
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import db, pipeline

app = FastAPI(title="YSPA – radar notizie")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
conn = db.connect()
db.seed_watchlist(conn)

VIEWS = {"alerts": "Segnalazioni", "watchlist": "Watchlist", "discover": "Scoperte", "all": "Tutte"}


@app.get("/")
def index(request: Request, view: str = "alerts"):
    return templates.TemplateResponse(request, "index.html", {
        "news": db.list_news(conn, view),
        "watchlist": db.get_watchlist(conn),
        "view": view,
        "views": VIEWS,
    })


@app.get("/api/news")
def api_news(view: str = "alerts"):
    return db.list_news(conn, view)


@app.post("/fetch")
def fetch_now():
    pipeline.run_once(conn)
    return RedirectResponse("/", status_code=303)


@app.post("/watchlist")
def add_ticker(ticker: str = Form(...), name: str = Form(...), aliases: str = Form(""), market: str = Form("US")):
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] or [name]
    db.add_to_watchlist(conn, ticker, name, alias_list, market)
    return RedirectResponse("/?view=watchlist", status_code=303)


@app.post("/watchlist/{ticker}/delete")
def delete_ticker(ticker: str):
    db.remove_from_watchlist(conn, ticker)
    return RedirectResponse("/?view=watchlist", status_code=303)


@app.post("/news/{news_id}/feedback")
def feedback(news_id: int, value: str = Form(...), view: str = Form("alerts")):
    if value in ("interessa", "ignora"):
        db.set_feedback(conn, news_id, value)
    return RedirectResponse(f"/?view={view}", status_code=303)
