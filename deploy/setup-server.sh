#!/usr/bin/env bash
# Installa o aggiorna il radar su un server Ubuntu (es. Oracle Cloud "Always Free").
#
#   curl -fsSL https://raw.githubusercontent.com/steestee25/yspa/claude/wonderful-franklin-ay2r0p/deploy/setup-server.sh | sudo bash
#
# Rieseguirlo aggiorna il codice e riavvia, senza toccare impostazioni e dati.
# Le impostazioni si possono passare come variabili d'ambiente (YSPA_SEC_USER_AGENT, YSPA_PASSWORD,
# YSPA_DOMAIN) per un'installazione senza domande.
set -euo pipefail

REPO="${YSPA_REPO:-https://github.com/steestee25/yspa.git}"
BRANCH="${YSPA_BRANCH:-claude/wonderful-franklin-ay2r0p}"
DIR="${YSPA_DIR:-/opt/yspa}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
has_tty() { { : < /dev/tty; } 2> /dev/null; }
ask() {  # ask "domanda" -> risposta da tastiera anche se lo script arriva da una pipe
  local answer=""
  read -r -p "$1 " answer < /dev/tty || true
  printf '%s' "$answer"
}

[ "$(id -u)" -eq 0 ] || { echo "Serve sudo: ... | sudo bash"; exit 1; }

say "1/5 Docker e git"
if ! command -v docker > /dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker > /dev/null 2>&1 || true
command -v git > /dev/null || { apt-get update -qq && apt-get install -y -qq git; }

say "2/5 Codice ($BRANCH)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH"
  git -C "$DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

say "3/5 Impostazioni"
if [ -f .env ]; then
  echo "Uso le impostazioni già presenti in $DIR/.env"
else
  sec_ua="${YSPA_SEC_USER_AGENT:-}"
  if [ -z "$sec_ua" ] && ! has_tty; then
    echo "Nessun terminale per le domande: imposta YSPA_SEC_USER_AGENT"; exit 1
  fi
  while [ -z "$sec_ua" ]; do
    sec_ua="$(ask 'Nome ed email per la SEC (es. Mario Rossi mario@esempio.com):')"
  done
  password="${YSPA_PASSWORD:-}"
  [ -n "$password" ] || password="$(openssl rand -base64 18 | tr -d '/+=')"
  domain="${YSPA_DOMAIN:-}"
  if [ -z "$domain" ]; then
    ip="$(curl -fsS4 https://api.ipify.org)"
    domain="${ip//./-}.sslip.io"
  fi
  umask 077
  cat > .env <<ENV
YSPA_SEC_USER_AGENT="$sec_ua"
YSPA_PASSWORD="$password"
YSPA_DOMAIN="$domain"
YSPA_TIMEZONE="Europe/Rome"
FINNHUB_API_KEY=""
ENV
  echo "Salvate in $DIR/.env"
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

say "4/5 Firewall (porte 80 e 443)"
# Le immagini Ubuntu di Oracle Cloud bloccano tutto tranne SSH con una regola REJECT in iptables.
if command -v iptables > /dev/null && iptables -S INPUT 2> /dev/null | grep -q -- "-j REJECT"; then
  for port in 80 443; do
    iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2> /dev/null \
      || iptables -I INPUT 1 -p tcp --dport "$port" -j ACCEPT
  done
  command -v netfilter-persistent > /dev/null && netfilter-persistent save > /dev/null 2>&1 || true
  echo "Porte aperte nel firewall del server. Ricorda di aprirle anche nella Security List di Oracle."
else
  echo "Nessuna regola da cambiare."
fi

say "5/5 Avvio"
docker compose --profile https up -d --build
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/health > /dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8000/health > /dev/null || { echo "La pagina non risponde: docker compose logs web"; exit 1; }

say "Fatto"
cat <<DONE
Indirizzo:  https://$YSPA_DOMAIN
Utente:     qualsiasi
Password:   $YSPA_PASSWORD

Log della raccolta:  cd $DIR && docker compose logs -f radar
Aggiornare:          rilancia lo stesso comando di installazione
DONE
