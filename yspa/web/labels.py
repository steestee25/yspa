"""Parole semplici al posto dei codici interni, per l'interfaccia."""

VIEWS = {
    "alerts": ("Da guardare", "Notizie sui tuoi titoli che possono muovere il prezzo."),
    "discover": ("Nuovi", "Notizie forti su aziende che non segui ancora."),
    "all": ("Tutte", "Tutto ciò che il radar ha letto, dalle più importanti."),
    "watchlist": ("I miei titoli", "Le aziende che il radar controlla per te."),
}

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
