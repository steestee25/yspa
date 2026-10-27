"""Prezzi: grafico Yahoo ricostruito sul caso Bending Spoons (14 ottobre 2026).

Chiusure dalle fonti citate in chat: 14/10 $53,46 (+41%), 22/10 $45,69; il 13/10 ($37,90) è ricavato dal +41%.
Il comunicato è uscito prima dell'apertura (11:00 UTC = 7:00 a New York).
"""
from datetime import datetime, timezone

import pytest

from yspa import db, pipeline, prices


def ts(s):
    return int(datetime.fromisoformat(s).timestamp())


def yahoo(times, closes, meta=None):
    return {"chart": {"result": [{
        "meta": {"symbol": "BSP", "currency": "USD", **(meta or {})},
        "timestamp": times,
        "indicators": {"quote": [{"close": closes}]},
    }], "error": None}}


DAILY = yahoo(
    [ts("2026-10-13T13:30:00+00:00"), ts("2026-10-14T13:30:00+00:00"), ts("2026-10-22T13:30:00+00:00")],
    [37.90, 53.46, 45.69],
    {"regularMarketPrice": 45.69, "regularMarketTime": ts("2026-10-22T20:00:00+00:00")},
)


def test_daily_price_before_premarket_news_is_previous_close():
    chart = prices.parse_chart(DAILY, prices.DAILY_SESSION_SECONDS)
    move = prices.move_since(chart, "2026-10-14T11:00:00+00:00")
    assert move["price_before"] == 37.90 and move["price_now"] == 45.69
    assert move["change_pct"] == pytest.approx(20.55, abs=0.01)


def test_news_during_session_ignores_the_unfinished_bar():
    chart = prices.parse_chart(DAILY, prices.DAILY_SESSION_SECONDS)
    assert chart.price_before(datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)) == 37.90


def test_intraday_bar_containing_news_is_excluded():
    data = yahoo([ts("2026-10-14T10:50:00+00:00"), ts("2026-10-14T10:55:00+00:00"), ts("2026-10-14T11:00:00+00:00")],
                 [38.0, 38.1, 47.0])
    chart = prices.parse_chart(data)
    # Notizia alle 11:02: la barra 11:00-11:05 contiene già la reazione.
    assert chart.price_before(datetime(2026, 10, 14, 11, 2, tzinfo=timezone.utc)) == 38.1


def test_null_bars_skipped_and_premarket_bar_newer_than_regular_price():
    data = yahoo([ts("2026-10-27T13:00:00+00:00"), ts("2026-10-27T13:05:00+00:00")], [None, 46.5],
                 {"regularMarketPrice": 45.69, "regularMarketTime": ts("2026-10-26T20:00:00+00:00")})
    chart = prices.parse_chart(data)
    assert chart.times == [ts("2026-10-27T13:05:00+00:00")] and chart.last_price == 46.5


def test_empty_chart():
    assert prices.parse_chart({"chart": {"result": None, "error": {"code": "Not Found"}}}) is None


def test_update_prices_one_chart_per_ticker():
    conn = db.connect(":memory:")
    base = dict(source="wire", summary="", url="", event_type="x", direction="su", reason="", in_watchlist=1, is_alert=1)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for i, (tick, score) in enumerate([("BSP", 7), ("BSP", 6), ("NKE", 2), ("APLD", 9)]):
        db.insert_news(conn, {**base, "uid": str(i), "title": f"n{i}", "tickers": [tick], "score": score,
                              "is_alert": int(score >= 5), "published_at": now.isoformat()})
    calls = []

    def fake_chart(symbol, since):
        calls.append(symbol)
        if symbol == "APLD":
            raise RuntimeError("429 Too Many Requests")
        return prices.Chart(symbol, "USD", [ts("2000-01-01T00:00:00+00:00")], [40.0], 50.0, 0)

    assert pipeline.update_prices(conn, fetch_chart=fake_chart) == 2
    assert sorted(calls) == ["APLD", "BSP"]  # NKE ha voto 2: niente prezzo
    bsp = [n for n in db.list_news(conn, "all") if n["tickers"] == ["BSP"]]
    assert {n["change_pct"] for n in bsp} == {25.0}


def test_italian_number_format():
    from yspa.web.timefmt import number, percent
    assert number(1234.5) == "1.234,50"
    assert percent(20.55) == "+20,6%" and percent(-3.04) == "−3,0%"
