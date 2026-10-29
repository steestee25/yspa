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
    assert chart.times == [ts("2026-10-27T13:05:00+00:00")] and chart.last == 46.5


def test_empty_chart():
    assert prices.parse_chart({"chart": {"result": None, "error": {"code": "Not Found"}}}) is None


def test_update_prices_only_alerts_and_watchlist_and_status():
    conn = db.connect(":memory:")
    base = dict(source="wire", summary="", url="", event_type="x", direction="su", reason="")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [("BSP", 7, 1, 1), ("BSP", 6, 1, 1), ("NKE", 2, 1, 0), ("APLD", 9, 1, 1), ("ACME", 6, 0, 0)]
    for i, (tick, score, wl, alert) in enumerate(rows):
        db.insert_news(conn, {**base, "uid": str(i), "title": f"n{i}", "tickers": [tick], "score": score,
                              "in_watchlist": wl, "is_alert": alert, "published_at": now.isoformat()})
    asked = {}

    def fake_quotes(requests, errors):
        asked.update(requests)
        errors["Yahoo"] = "SourceBlocked: Yahoo ha rifiutato (429)"
        return {"BSP": prices.Quote("BSP", "CNBC", 50.0, int(now.timestamp()), "USD", 48.0)}

    assert pipeline.update_prices(conn, quotes_for=fake_quotes) == 2
    assert sorted(asked) == ["APLD", "BSP"]  # NKE ha voto 2, ACME non è né segnalata né seguita
    bsp = [n for n in db.list_news(conn, "all") if n["tickers"] == ["BSP"]]
    # Senza barre il prezzo "prima" è quello del primo rilevamento: variazione 0, base dichiarata.
    assert {(n["price_basis"], n["change_pct"], n["day_change_pct"]) for n in bsp} == {("rilevamento", 0.0, 4.17)}
    status = {s["name"]: s for s in db.get_source_status(conn)}
    assert status["Prezzi · Yahoo"]["ok"] == 0 and "429" in status["Prezzi · Yahoo"]["detail"]
    assert status["Prezzi · CNBC"]["ok"] == 1
    # Subito dopo non si richiede di nuovo: ogni notizia si riprezza al massimo ogni 5 minuti.
    assert pipeline.update_prices(conn, quotes_for=fake_quotes) == 0


def test_detection_price_is_kept_on_later_updates():
    t0 = ts("2026-10-29T14:00:00+00:00")
    first = prices.move_since(prices.Quote("LDO.MI", "CNBC", 50.0, t0, "EUR", 49.0), "2026-10-29T13:58:00+00:00")
    later = prices.move_since(prices.Quote("LDO.MI", "CNBC", 51.0, t0 + 600, "EUR", 49.0), "2026-10-29T13:58:00+00:00", first)
    assert first["price_basis"] == "rilevamento" and later["price_before"] == 50.0 and later["change_pct"] == 2.0


def test_nasdaq_bars_give_price_before_news():
    # Formato reale della risposta Nasdaq (MRNA, 29/10/2026), ridotto a tre barre.
    data = {"data": {"lastSalePrice": "$218.20", "previousClose": "$214.165", "chart": [
        {"x": 1793266140000, "y": 216.37}, {"x": 1793266200000, "y": 216.2501}, {"x": 1793266260000, "y": 219.17}]}}
    quote = prices.parse_nasdaq("MRNA", data)
    move = prices.move_since(quote, "2026-10-29T13:30:30+00:00")  # 9:30:30 a New York
    assert move["price_before"] == 216.37 and move["price_basis"] == "notizia" and move["price_now"] == 218.2
    assert quote.day_change_pct == 1.88
    # Notizia uscita ieri sera, prima delle barre di oggi: il prezzo prima è la chiusura di ieri.
    assert prices.move_since(quote, "2026-10-28T22:00:00+00:00")["price_before"] == 214.165


def test_cnbc_parse_real_format():
    # Campi reali di CNBC (29/10/2026): numeri con virgole, codice 1 = simbolo sconosciuto.
    data = {"FormattedQuoteResult": {"FormattedQuote": [
        {"symbol": "RHM-DE", "code": 0, "last": "1,050.80", "last_time": "2026-10-29T14:55:22.000+0100",
         "previous_day_closing": "1,012.00", "currencyCode": "EUR"},
        {"symbol": "MRNA", "code": 0, "last": "218.31", "last_time": "2026-10-29T10:13:02.697-0400",
         "previous_day_closing": "214.17", "currencyCode": "USD",
         "ExtendedMktQuote": {"last": "217.00", "last_time": "2026-10-29T09:29:38.161-0400"}},
        {"symbol": "NOVOB-DK", "code": 1, "last": None}]}}
    quotes = prices.parse_cnbc(data, {"RHM-DE": "RHM.DE", "MRNA": "MRNA", "NOVOB-DK": "NOVO-B.CO"})
    assert set(quotes) == {"RHM.DE", "MRNA"}
    assert quotes["RHM.DE"].last == 1050.8 and quotes["RHM.DE"].day_change_pct == 3.83
    assert quotes["MRNA"].last == 218.31  # il pre-market (09:29) è più vecchio della seduta (10:13)


def test_cnbc_symbol_mapping():
    assert prices.to_cnbc("MRNA") == "MRNA"
    assert prices.to_cnbc("RHM.DE") == "RHM-DE" and prices.to_cnbc("ASML.AS") == "ASML-NL"
    assert prices.to_cnbc("NOVO-B.CO") == "NOVOB-DK" and prices.to_cnbc("XYZ.KS") is None


def test_italian_number_format():
    from yspa.web.timefmt import number, percent
    assert number(1234.5) == "1.234,50"
    assert percent(20.55) == "+20,6%" and percent(-3.04) == "−3,0%"


def test_previous_close_rule_skips_weekend_and_older_news():
    # Barre di lunedì 2 novembre: la chiusura precedente è venerdì 30 ottobre alle 16:00 (New York).
    monday = {"data": {"lastSalePrice": "$10.00", "previousClose": "$9.00", "chart": [{"x": 1793592000000, "y": 9.5}]}}
    quote = prices.parse_nasdaq("ABC", monday)
    assert prices.move_since(quote, "2026-10-31T12:00:00+00:00")["price_before"] == 9.0      # sabato
    assert prices.move_since(quote, "2026-10-30T19:00:00+00:00")["price_basis"] == "rilevamento"  # venerdì prima della chiusura
