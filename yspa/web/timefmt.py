"""Testo dei titoli: quelli tutti in maiuscolo diventano frasi normali."""


def calm_title(title: str) -> str:
    """Un titolo tutto in maiuscolo diventa 'Frase normale': in un elenco sobrio, il maiuscolo urla."""
    letters = [c for c in title if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        lowered = title.lower()
        return lowered[:1].upper() + lowered[1:]
    return title
