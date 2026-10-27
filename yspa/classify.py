"""Classificazione a regole (gratuita) delle notizie.

Ogni regola associa frasi tipiche a un tipo di evento, una direzione attesa del prezzo
e un punteggio di importanza da 1 a 10. Vince la regola con il punteggio più alto.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    event_type: str
    direction: str  # "su", "giù", "incerta"
    score: int
    patterns: tuple[str, ...]


RULES = [
    Rule("fallimento", "giù", 10, (r"chapter 11", r"bankruptcy", r"insolvenc")),
    Rule("studio clinico positivo", "su", 9, (
        r"met (its|the) primary endpoint", r"positive (topline|top-line|phase \d)",
        r"statistically significant", r"achieved (its|the) primary endpoint",
    )),
    Rule("studio clinico negativo", "giù", 9, (
        r"did not meet (its|the) primary endpoint", r"failed to meet", r"discontinu\w+ (the )?(trial|program|development)",
    )),
    Rule("acquisizione / OPA", "su", 9, (
        r"to be acquired", r"definitive (merger )?agreement", r"tender offer", r"agreed to acquire",
        r"to acquire .{0,60} for \$", r"merger agreement", r"takeover", r"offerta pubblica",
    )),
    Rule("approvazione farmaco", "su", 8, (
        r"fda approv", r"approved by the (u\.s\. )?fda", r"chmp (adopted a )?positive opinion",
        r"european commission approv", r"granted (marketing )?approval",
    )),
    Rule("rifiuto farmaco", "giù", 8, (r"complete response letter", r"\bcrl\b", r"negative opinion")),
    Rule("investimento strategico", "su", 7, (
        r"strategic investment", r"private placement", r"berkshire hathaway",
        r"acquires? (a )?\d+(\.\d+)?% stake", r"increases? (its )?stake",
    )),
    Rule("guidance alzata", "su", 7, (r"raises? (its )?(full[- ]year )?(guidance|outlook|forecast)",)),
    Rule("guidance abbassata", "giù", 7, (r"lowers? (its )?(full[- ]year )?(guidance|outlook|forecast)", r"profit warning")),
    Rule("ingresso in indice", "su", 6, (
        r"(joins?|added to|to replace .{0,40} in) the (s&p 500|nasdaq-100|s&p midcap 400|stoxx|ftse mib|dax)",
    )),
    Rule("contratto importante", "su", 6, (
        r"awarded .{0,40}contract", r"multi-year (agreement|contract)", r"\$\d+(\.\d+)? (billion|bn) (contract|deal|agreement)",
    )),
    Rule("aumento di capitale", "giù", 6, (
        r"public offering", r"at-the-market", r"pricing of .{0,40}offering", r"aumento di capitale",
    )),
    Rule("risultati trimestrali", "incerta", 5, (
        r"(first|second|third|fourth) quarter .{0,30}results", r"\bq[1-4] (20\d\d )?(financial )?results",
        r"reports? .{0,40}(quarter|full[- ]year) .{0,20}results",
    )),
    Rule("cambio management", "incerta", 4, (r"appoints? .{0,40}(chief executive|ceo)", r"(ceo|chief executive) .{0,20}(resign|step down|depart)")),
]

# Voci degli 8-K della SEC: sono strutturate, quindi non serve leggere il testo.
SEC_ITEMS = {
    "1.01": ("accordo rilevante", "incerta", 6),
    "1.03": ("fallimento", "giù", 10),
    "2.01": ("acquisizione completata", "incerta", 6),
    "2.02": ("risultati trimestrali", "incerta", 5),
    "3.02": ("vendita di azioni non registrate", "incerta", 6),
    "4.02": ("bilanci non affidabili", "giù", 8),
    "5.02": ("cambio management", "incerta", 4),
    "7.01": ("comunicazione al mercato", "incerta", 3),
    "8.01": ("altri eventi", "incerta", 3),
}

_COMPILED = [(rule, [re.compile(p, re.IGNORECASE) for p in rule.patterns]) for rule in RULES]


@dataclass
class Classification:
    event_type: str = "altro"
    direction: str = "neutra"
    score: int = 1
    reason: str = ""


def classify_text(text: str) -> Classification:
    best = Classification()
    for rule, patterns in _COMPILED:
        if rule.score <= best.score:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                best = Classification(rule.event_type, rule.direction, rule.score, f'frase: "{match.group(0)}"')
                break
    return best


def classify_sec_items(items: list[str]) -> Classification:
    best = Classification()
    for item in items:
        if item in SEC_ITEMS:
            event_type, direction, score = SEC_ITEMS[item]
            if score > best.score:
                best = Classification(event_type, direction, score, f"8-K voce {item}")
    return best


def classify(text: str, sec_items: list[str] | None = None) -> Classification:
    """Combina testo e voci SEC: tiene il risultato più importante."""
    by_text = classify_text(text)
    by_items = classify_sec_items(sec_items or [])
    return by_text if by_text.score >= by_items.score else by_items
