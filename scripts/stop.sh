#!/usr/bin/env bash
# Ferma raccolta e pagina web avviate da start.sh.
cd "$(dirname "$0")/.."
for name in radar web; do
  if [ -f "data/$name.pid" ] && kill "$(cat "data/$name.pid")" 2> /dev/null; then
    echo "Fermato: $name"
  fi
  rm -f "data/$name.pid"
done
