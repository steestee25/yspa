"""Uso:
    python -m yspa run --every 60          # raccolta continua, ogni 60 secondi
    python -m yspa fetch --report          # un giro di raccolta con riepilogo
    python -m yspa quotes MRNA RHM.DE      # prezzi in tempo reale (senza simboli: la watchlist)
    python -m yspa price BSP --since 2026-10-14T11:00:00+00:00   # quanto si è mosso da una notizia
    python -m yspa status                  # stato delle fonti
    python -m yspa export                  # notizie salvate in JSON, una per riga
"""
import argparse
import json
import logging
import signal
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import db, pipeline, prices

log = logging.getLogger("yspa")


def print_alerts(alerts: list[dict]) -> None:
    for a in alerts:
        print(f"[{a['score']}/10] {', '.join(a['tickers'])} – {a['event_type']} ({a['direction']}): {a['title']}\n    {a['url']}")


def print_status(conn) -> None:
    for s in db.get_source_status(conn):
        state = "ok     " if s["ok"] else "ERRORE "
        print(f"  {state} {s['name']:20} {s['items']:4d} elementi · controllata {s['checked_at']}"
              f"{' · ' + s['detail'] if s['detail'] else ''}")


def print_report(conn) -> None:
    """Riepilogo di tutto ciò che c'è nel database: fonti, segnalazioni, notizie più importanti."""
    news = db.list_news(conn, "all", limit=100000)
    print(f"\n=== REPORT: {len(news)} notizie, {sum(n['is_alert'] for n in news)} segnalazioni ===")
    print("\nStato delle fonti:")
    print_status(conn)
    print("\nPer fonte:")
    for source, count in Counter(n["source"] for n in news).most_common():
        print(f"  {count:5d}  {source}")
    print("\nPer tipo di evento:")
    for event, count in Counter(n["event_type"] for n in news).most_common():
        print(f"  {count:5d}  {event}")
    print("\nNotizie più importanti:")
    top = sorted(news, key=lambda n: (n["is_alert"], n["score"], n["published_at"]), reverse=True)[:60]
    for n in top:
        flag = "SEGNALAZIONE" if n["is_alert"] else "            "
        where = "watchlist" if n["in_watchlist"] else "scoperta "
        price = ""
        if n.get("change_pct") is not None:
            price = f" | {n['price_before']}→{n['price_now']} {n['currency']} ({n['change_pct']:+.2f}% {n['price_basis']}, {n['price_source']})"
        print(f"  {flag} [{n['score']}/10 {n['direction']:7}] {where} {','.join(n['tickers']) or '-':14} "
              f"{n['published_at'][:16]} {n['event_type']} | {n['title'][:100]}{price} | {n['url']}")


def print_quotes(symbols: list[str]) -> None:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    errors: dict[str, str] = {}
    quotes = prices.best_quotes({s: since for s in symbols}, errors)
    for symbol in symbols:
        q = quotes.get(symbol)
        if q is None:
            print(f"  {symbol:12} nessuna fonte ha il prezzo")
            continue
        at = datetime.fromtimestamp(q.last_time, timezone.utc).isoformat(timespec="seconds")
        day = f"{q.day_change_pct:+.2f}% oggi" if q.day_change_pct is not None else "variazione di oggi n.d."
        bars = f"{len(q.times)} barre" if q.times else "senza barre"
        print(f"  {symbol:12} {q.last:>12,.4f} {q.currency:3} · {day} · ora {at} · fonte {q.source} ({bars})")
    for source, err in errors.items():
        print(f"  [fonte {source}] {err}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="yspa")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--report", action="store_true", help="stampa un riepilogo alla fine")
    run = sub.add_parser("run")
    run.add_argument("--every", type=int, default=60, help="secondi tra un giro e l'altro")
    run.add_argument("--cycles", type=int, default=0, help="numero di giri (0 = senza fine)")
    run.add_argument("--report", action="store_true", help="stampa un riepilogo alla fine")
    quotes = sub.add_parser("quotes")
    quotes.add_argument("symbols", nargs="*")
    price = sub.add_parser("price")
    price.add_argument("symbol")
    price.add_argument("--since", required=True, help="istante della notizia, ISO 8601 con fuso orario")
    sub.add_parser("status")
    sub.add_parser("export")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    conn = db.connect()
    db.seed_watchlist(conn)

    if args.command == "quotes":
        print_quotes(args.symbols or [w["ticker"] for w in db.get_watchlist(conn)])
        return
    if args.command == "price":
        try:
            quote = prices.yahoo_chart(args.symbol, datetime.fromisoformat(args.since))
        except Exception as exc:
            print(f"{args.symbol}: prezzo storico non disponibile ({prices._short(exc)})")
            return
        print(f"{args.symbol}: {prices.move_since(quote, args.since) if quote else 'prezzo non disponibile'}")
        return
    if args.command == "status":
        print_status(conn)
        return
    if args.command == "export":
        for n in db.list_news(conn, "all", limit=100000):
            print(json.dumps(n, ensure_ascii=False))
        return

    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        log.info("Arresto richiesto: termino il giro in corso")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    cycles = 1 if args.command == "fetch" else args.cycles
    done = 0
    while not stopping:
        started = time.monotonic()
        try:
            alerts = pipeline.run_once(conn)
            log.info("Giro %d completato: %d nuove segnalazioni", done + 1, len(alerts))
            print_alerts(alerts)
        except Exception:  # un giro andato male non deve fermare la raccolta
            log.exception("Giro %d fallito, riprovo al prossimo", done + 1)
        done += 1
        if cycles and done >= cycles:
            break
        # Attesa a piccoli passi, così l'arresto non deve aspettare un minuto intero.
        while not stopping and time.monotonic() - started < args.every:
            time.sleep(1)
    if args.report:
        print_report(conn)


if __name__ == "__main__":
    main()
