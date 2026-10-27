"""Interfaccia web: feed delle notizie, segnalazioni, watchlist.

Avvio: uvicorn yspa.web.app:app --reload
"""
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config, db, pipeline
from .timefmt import human_time

app = FastAPI(title="YSPA")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["when"] = human_time
conn = db.connect()
db.seed_watchlist(conn)

VIEWS = {"alerts": "Segnalazioni", "discover": "Scoperte", "all": "Tutte", "watchlist": "Watchlist"}
SORT_LABELS = {"importanza": "Importanza", "recenti": "Più recenti"}


def back_to(view: str, sort: str) -> RedirectResponse:
    return RedirectResponse("/?" + urlencode({"view": view, "sort": sort}), status_code=303)


@app.get("/")
def index(request: Request, view: str = "alerts", sort: str = "importanza"):
    view = view if view in VIEWS else "alerts"
    sort = sort if sort in SORT_LABELS else "importanza"
    news = [] if view == "watchlist" else db.list_news(conn, view, sort=sort)
    return templates.TemplateResponse(request, "index.html", {
        "news": news,
        "near": db.near_alerts(conn) if view == "alerts" and not news else [],
        "watchlist": db.get_watchlist(conn),
        "last_fetch": db.last_fetch(conn),
        "view": view,
        "views": VIEWS,
        "sort": sort,
        "sorts": SORT_LABELS,
        "feedback_min_score": config.ALERT_SCORE_WATCHLIST,
    })


@app.get("/api/news")
def api_news(view: str = "alerts", sort: str = "importanza"):
    return db.list_news(conn, view, sort=sort)


@app.post("/fetch")
def fetch_now(view: str = Form("alerts"), sort: str = Form("importanza")):
    pipeline.run_once(conn)
    return back_to(view, sort)


@app.post("/watchlist")
def add_ticker(ticker: str = Form(...), name: str = Form(...), aliases: str = Form(""), market: str = Form("US")):
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] or [name]
    db.add_to_watchlist(conn, ticker, name, alias_list, market)
    return back_to("watchlist", "importanza")


@app.post("/watchlist/{ticker}/delete")
def delete_ticker(ticker: str):
    db.remove_from_watchlist(conn, ticker)
    return back_to("watchlist", "importanza")


@app.post("/news/{news_id}/feedback")
def feedback(news_id: int, value: str = Form(...), view: str = Form("alerts"), sort: str = Form("importanza")):
    if value in ("interessa", "ignora"):
        db.set_feedback(conn, news_id, value)
    return back_to(view, sort)
