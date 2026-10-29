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
6. **Pagina web** (una sola pagina, si aggiorna da sola ogni minuto):
   - ricerca tra circa 10.000 società quotate negli USA (elenco SEC) e inserimento a mano dei titoli
     europei scegliendo la borsa; **Segui** aggiunge il titolo, i tre puntini lo tolgono;
   - una scheda per ogni titolo seguito: prezzo, variazione di oggi, grafico della giornata, ultima notizia
     (su telefono diventano righe, come nell'app Azioni);
   - "Da guardare" con le segnalazioni, notizie filtrabili, stato delle fonti.
   `data.json` contiene i dati della pagina, `/health` lo stato delle fonti.

## Su GitHub, gratis e senza carta (consigliato per iniziare)

Il workflow `.github/workflows/pages.yml` esegue un giro di raccolta ogni 5 minuti circa e pubblica la
pagina su **https://steestee25.github.io/yspa/**. Per un repository pubblico non costa nulla.
Ogni giro avvia il successivo; per fermare il radar: scheda *Actions* → *pages* → *Disable workflow*.

Da fare una volta sola:
1. GitHub → repository → **Settings → Pages** → *Build and deployment* → *Source*: **GitHub Actions**.
2. (Consigliato) **Settings → Secrets and variables → Actions → New repository secret**:
   nome `YSPA_SEC_USER_AGENT`, valore `Nome Cognome tua@email.com`.
3. Per aggiungere e togliere titoli dalla pagina: rotellina in alto → crea un token su
   <https://github.com/settings/personal-access-tokens/new> con accesso solo a questo repository e
   permesso **Contents: Read and write**, e incollalo. Il token resta in quel browser; la pagina modifica
   `watchlist.csv` e il radar segue il nuovo titolo dal giro successivo.

Differenze rispetto a un server: la pagina è pubblica e si legge soltanto; la watchlist si cambia
modificando `watchlist.csv`; GitHub esegue i giri ogni 5 minuti, a volte in ritardo; da GitHub
rispondono PR Newswire e i prezzi Nasdaq/CNBC, mentre GlobeNewswire e (senza email) la SEC no.
GitHub sospende i workflow programmati dopo 60 giorni senza attività sul repository: basta
riattivarli dalla scheda *Actions*.

## Server cloud gratuito (Oracle Cloud "Always Free")

Una macchina sempre accesa, gratis. Oracle chiede una carta solo per verificare l'identità:
le risorse "Always Free" non vengono addebitate.

1. **Account**: registrati su <https://cloud.oracle.com> (scegli una regione vicina, es. Milano o Francoforte:
   non si cambia dopo).
2. **Macchina**: menu ☰ → *Compute* → *Instances* → *Create instance*.
   - *Image*: **Ubuntu 24.04**.
   - *Shape*: **VM.Standard.A1.Flex** (Ampere) con 1 OCPU e 6 GB, contrassegnata "Always Free-eligible".
     Se dice "Out of capacity", usa **VM.Standard.E2.1.Micro** (anche lei gratuita).
   - *Add SSH keys*: **Generate a key pair for me** e scarica la chiave privata.
   - *Create*. Annota il **Public IP address**.
3. **Porte 80 e 443**: nella pagina dell'istanza → *Subnet* → *Security Lists* → *Default Security List*
   → *Add Ingress Rules*: Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port Range `80,443`.
4. **Collegati** dal tuo computer (Mac/Linux: Terminale; Windows: PowerShell):
   ```bash
   ssh -i chiave-scaricata.key ubuntu@IP-DEL-SERVER
   ```
5. **Installa** (un comando; chiede nome ed email per la SEC):
   ```bash
   curl -fsSL https://raw.githubusercontent.com/steestee25/yspa/claude/wonderful-franklin-ay2r0p/deploy/setup-server.sh | sudo bash
   ```
   Alla fine stampa indirizzo (`https://IP-con-trattini.sslip.io`) e password. Il certificato HTTPS si
   ottiene da solo in circa un minuto.
6. **Aggiornare**: rilancia lo stesso comando. Impostazioni e dati restano.

## Avvio in produzione (Docker)

Su un computer o server sempre acceso:

```bash
cp .env.example .env      # poi compila YSPA_SEC_USER_AGENT e, se esposto in rete, YSPA_PASSWORD
docker compose up -d
```

Pagina su `http://localhost:8000` (solo da quel computer; `YSPA_BIND=0.0.0.0` per la rete di casa).
Due servizi: `radar` (raccolta) e `web` (pagina), con riavvio automatico e database in `./data`.
Con `--profile https` parte anche Caddy, che espone la pagina in HTTPS su `YSPA_DOMAIN`.
Log: `docker compose logs -f radar`.

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
