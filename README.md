# YSPA – radar notizie per azioni

Legge ogni minuto i comunicati delle aziende e i depositi ufficiali alla SEC, riconosce quelli che
possono muovere il prezzo di un'azione e te li mostra con quanto il titolo si è già mosso.
Non compra né vende nulla: segnala, decidi tu. Non è consulenza finanziaria.

## Cosa fa

1. **Raccoglie** (ogni 60 secondi):
   - **SEC EDGAR**: 8-K (aziende USA), 6-K (aziende estere quotate in USA), SC 13D (investitori sopra il 5%);
   - **comunicati stampa**: GlobeNewswire e PR Newswire; se una notizia importante non ha il ticker
     nel feed, lo cerca nel primo paragrafo della pagina completa;
   - **Finnhub** (facoltativo, chiave gratuita): notizie per ogni titolo USA della watchlist.
2. **Riconosce il titolo**: dai tag tipo `(NASDAQ: MRNA)` o `(Euronext Paris: MC)` → `MC.PA`,
   dal codice SEC dell'azienda, o dal nome della watchlist nel titolo della notizia.
3. **Classifica** con regole (`yspa/classify.py`): tipo di evento, effetto atteso, importanza 1–10.
   I depositi SEC si classificano dal codice della voce (es. 1.01 = accordo importante).
4. **Segnala**: titoli seguiti da 5/10 in su; titoli nuovi solo da 8/10 in su.
5. **Prezzi**, per segnalazioni e titoli seguiti, in catena:
   Yahoo Finance (storico) → Nasdaq (barre al minuto di oggi, solo USA) → CNBC (ultimo prezzo, USA ed Europa).
   Il prezzo "prima" è quello prima della notizia quando le barre lo coprono; altrimenti quello del primo
   controllo del radar, e la pagina lo dice.
6. **Pagina web**: da guardare, titoli nuovi, tutte le notizie, watchlist modificabile, risposte
   "Mi interessa / Ignora", stato di ogni fonte. `/health` restituisce lo stato in JSON.

## Avvio in produzione (Docker)

Su un computer o server sempre acceso:

```bash
cp .env.example .env      # poi compila YSPA_SEC_USER_AGENT e, se esposto in rete, YSPA_PASSWORD
docker compose up -d
```

Pagina su `http://localhost:8000`. Due servizi: `radar` (raccolta) e `web` (pagina), con riavvio
automatico e database in `./data`. Log: `docker compose logs -f radar`.

## Avvio senza Docker

```bash
pip install -r requirements.txt
export YSPA_SEC_USER_AGENT="Nome Cognome tua@email.com"
bash scripts/start.sh     # raccolta + pagina web sulla porta 8000; bash scripts/stop.sh per fermare
```

## Avvio su GitHub Codespaces

1. Su GitHub scegli il branch `claude/wonderful-franklin-ay2r0p`, poi **Code → Codespaces → Create codespace**.
2. Inserisci il secret `YSPA_SEC_USER_AGENT` (nome ed email).
3. Tutto si avvia da solo; la pagina è sulla porta 8000 (scheda **Ports**).

Un Codespace si spegne dopo 30 minuti senza attività: va bene per provare, non per la guardia continua.

## Comandi utili

```bash
python -m yspa quotes                # prezzi in tempo reale della watchlist, con la fonte usata
python -m yspa quotes MC.PA SAP.DE   # prezzi di altri titoli (formato Yahoo)
python -m yspa status                # stato delle fonti
python -m yspa fetch --report        # un giro di raccolta con riepilogo
python -m pytest                     # test (pip install -r requirements-dev.txt)
```

## Limiti noti, verificati

- **SEC**: rifiuta le richieste senza un User-Agent con nome ed email veri. Da GitHub Actions con un
  indirizzo `noreply` risponde 403; da Codespaces con un'email vera ha risposto.
- **Yahoo**: dai server cloud risponde 429; la catena passa a Nasdaq e CNBC. Da casa di solito risponde.
- **CNBC**: non trova Novo Nordisk (`NOVOB-DK`); altri titoli verificati: RHM-DE, ASML-NL, ARGX-BE, STMMI-IT, LDO-IT.
- **Europa**: le notizie arrivano solo se passano per GlobeNewswire o PR Newswire; le fonti
  regolamentate per paese (Borsa Italiana, Euronext, EQS) non sono ancora collegate.
- **Regole in inglese**: comunicati in altre lingue ricevono voti bassi.
- **Notifiche** sul telefono: non ancora (prossimo passo: Telegram).
