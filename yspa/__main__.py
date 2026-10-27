"""Uso:
    python -m yspa fetch            # un giro di raccolta
    python -m yspa run --every 60   # raccolta continua, ogni 60 secondi
    python -m yspa price BSP --since 2026-10-14T11:00:00+00:00   # quanto si è mosso da allora
"""
import argparse
import logging
import time
from collections import Counter
from datetime import datetime

from . import db, pipeline, prices


def print_alerts(alerts: list[dict]) -> None:
    for a in alerts:
        print(f"[{a['score']}/10] {', '.join(a['tickers'])} – {a['event_type']} ({a['direction']}): {a['title']}\n    {a['url']}")


def print_report(conn) -> None:
    """Riepilogo di tutto ciò che c'è nel database: fonti, segnalazioni, notizie più importanti."""
    news = db.list_news(conn, "all", limit=100000)
    print(f"\n=== REPORT: {len(news)} notizie, {sum(n['is_alert'] for n in news)} segnalazioni ===")
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
        print(f"  {flag} [{n['score']}/10 {n['direction']:7}] {where} {','.join(n['tickers']) or '-':14} "
              f"{n['published_at'][:16]} {n['event_type']} | {n['title'][:110]} | {n['url']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="yspa")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--report", action="store_true", help="stampa un riepilogo alla fine")
    price = sub.add_parser("price")
    price.add_argument("symbol")
    price.add_argument("--since", required=True, help="istante della notizia, ISO 8601 con fuso orario")
    run = sub.add_parser("run")
    run.add_argument("--every", type=int, default=60, help="secondi tra un giro e l'altro")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "price":
        chart = prices.fetch_chart(args.symbol, datetime.fromisoformat(args.since))
        move = prices.move_since(chart, args.since) if chart else None
        print(f"{args.symbol}: {move or 'prezzo non disponibile'}")
        return
    conn = db.connect()
    db.seed_watchlist(conn)

    while True:
        alerts = pipeline.run_once(conn)
        logging.info("Nuove segnalazioni: %d", len(alerts))
        print_alerts(alerts)
        if args.command == "fetch":
            if args.report:
                print_report(conn)
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
