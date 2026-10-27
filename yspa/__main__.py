"""Uso:
    python -m yspa fetch            # un giro di raccolta
    python -m yspa run --every 60   # raccolta continua, ogni 60 secondi
"""
import argparse
import logging
import time

from . import db, pipeline


def print_alerts(alerts: list[dict]) -> None:
    for a in alerts:
        print(f"[{a['score']}/10] {', '.join(a['tickers'])} – {a['event_type']} ({a['direction']}): {a['title']}\n    {a['url']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="yspa")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch")
    run = sub.add_parser("run")
    run.add_argument("--every", type=int, default=60, help="secondi tra un giro e l'altro")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = db.connect()
    db.seed_watchlist(conn)

    while True:
        alerts = pipeline.run_once(conn)
        logging.info("Nuove segnalazioni: %d", len(alerts))
        print_alerts(alerts)
        if args.command == "fetch":
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
