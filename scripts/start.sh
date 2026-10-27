#!/usr/bin/env bash
# Avvia la raccolta (ogni 60 secondi) e la pagina web sulla porta 8000, in background.
# Se sono già attivi non li riavvia, così si può rieseguire senza creare doppioni.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data

if [ -z "${YSPA_SEC_USER_AGENT:-}" ]; then
  echo "Attenzione: YSPA_SEC_USER_AGENT non è impostato, la SEC verrà saltata."
fi

running() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2> /dev/null; }

if running data/radar.pid; then
  echo "Raccolta già attiva"
else
  nohup python -m yspa run --every 60 > data/radar.log 2>&1 &
  echo $! > data/radar.pid
  echo "Raccolta avviata (log: data/radar.log)"
fi

if running data/web.pid; then
  echo "Pagina web già attiva"
else
  nohup python -m uvicorn yspa.web.app:app --host 0.0.0.0 --port 8000 > data/web.log 2>&1 &
  echo $! > data/web.pid
  echo "Pagina web avviata sulla porta 8000 (log: data/web.log)"
fi

echo "Per vedere cosa succede: tail -f data/radar.log"
