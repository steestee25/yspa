"""Parole semplici al posto dei codici interni, per l'interfaccia."""

EFFECTS = {
    "su": "Può far salire il prezzo",
    "giù": "Può far scendere il prezzo",
}


def importance(score: int) -> str:
    level = "alta" if score >= 8 else "media" if score >= 5 else "bassa"
    return f"Importanza {level} ({score} su 10)"


def effect(direction: str) -> str:
    return EFFECTS.get(direction, "Effetto sul prezzo incerto")


def event(event_type: str) -> str:
    return "Notizia generica" if event_type == "altro" else event_type[:1].upper() + event_type[1:]


def source(name: str) -> str:
    if name.startswith("SEC "):
        return f"Documento ufficiale alla SEC ({name[4:]})"
    if name.startswith("Finnhub/"):
        return f"Notizia · {name.split('/', 1)[1] or 'Finnhub'}"
    return {
        "globenewswire": "Comunicato stampa · GlobeNewswire",
        "prnewswire": "Comunicato stampa · PR Newswire",
    }.get(name, name)


def reason(text: str) -> str:
    if text.startswith('frase: "'):
        return f"Nel testo compare «{text[8:-1]}»."
    if text.startswith("8-K voce "):
        return f"Il documento depositato alla SEC indica la voce {text[9:]}."
    if text.startswith("SEC "):
        return f"È un modulo {text[4:]} depositato alla SEC."
    return text


def source_error(detail: str) -> str:
    """L'errore tecnico di una fonte, detto in parole semplici."""
    if "YSPA_SEC_USER_AGENT" in detail:
        return "Manca il tuo nome ed email per la SEC (impostazione YSPA_SEC_USER_AGENT)."
    if "403" in detail:
        return "Rifiuta le richieste da questo computer (errore 403): succede spesso dai server cloud."
    if "429" in detail:
        return "Ha ricevuto troppe richieste da questo computer (errore 429): il radar riprova più tardi."
    if "in pausa" in detail:
        return "In pausa dopo un rifiuto: il radar riprova tra qualche minuto."
    if "Timeout" in detail or "ConnectError" in detail:
        return "Non raggiungibile in questo momento (rete o sito lento)."
    if "senza notizie" in detail:
        return "Ha risposto, ma senza notizie: il feed potrebbe essere cambiato."
    return detail
