# YSPA – radar notizie per azioni

Controlla le notizie al posto tuo e segnala quelle che possono muovere il prezzo di un'azione.
Non compra né vende nulla: ti segnala, decidi tu. Non è consulenza finanziaria.

## Cosa fa (fase 1)

1. **Raccoglie** notizie da fonti gratuite:
   - **SEC EDGAR**: 8-K (aziende USA), 6-K (aziende estere quotate in USA, es. Bending Spoons), SC 13D;
   - **comunicati stampa** via RSS: GlobeNewswire, PR Newswire, BusinessWire;
   - **Finnhub** (facoltativo, chiave gratuita): notizie per ogni titolo USA in watchlist.
2. **Riconosce il titolo**: dal tag `(NASDAQ: MRNA)`, dal CIK della SEC o dagli alias della watchlist.
3. **Classifica** con regole gratuite (`yspa/classify.py`): tipo di evento, direzione attesa, punteggio 1–10.
4. **Segnala**:
   - titolo in watchlist → segnalazione da punteggio 5;
   - titolo fuori watchlist → segnalazione ("Scoperte") solo da punteggio 8.
5. **Web**: feed, watchlist modificabile, pulsanti "Mi interessa / Ignora".

## Avvio

```bash
pip install -r requirements.txt
export YSPA_SEC_USER_AGENT="Nome Cognome tua@email.com"   # obbligatorio per la SEC
export FINNHUB_API_KEY=...                                 # facoltativo

python -m yspa run --every 60          # raccolta continua, ogni 60 secondi
uvicorn yspa.web.app:app --reload      # interfaccia web su http://127.0.0.1:8000
```

Test: `python -m pytest`

## Limiti noti

- L'Europa è coperta solo dai comunicati che passano per i wire RSS e dagli alias. Le fonti
  regolamentate per paese (Borsa Italiana, Euronext, EQS) arrivano nella fase successiva.
- Le regole sono parole chiave in inglese: notizie in italiano o tedesco vengono riconosciute meno.
- Gli URL dei feed RSS sono in `yspa/config.py`; se uno cambia, basta aggiornarlo lì.

## Prossime fasi

2. Lettura del testo completo dei depositi SEC (esibito 99.1) e fonti europee.
3. Calendario dei catalizzatori: trimestrali, IPO, studi clinici, EMA, cambi degli indici.
4. Radar: volumi anomali, vendite allo scoperto, notizie positive che si accumulano.
5. Diario dei risultati: prezzo a +1 ora, +1 giorno e +5 giorni dopo ogni segnalazione.
6. Notifiche Telegram e app.
