"""Ambiente dei modelli di pagina, condiviso tra server web e sito statico."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"


def environment() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
