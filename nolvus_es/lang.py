"""Detección rápida (heurística) de si un texto está en inglés, en español o es neutro.

Neutro = nombres propios, números o textos que se escriben igual en ambos idiomas
("Riften", "Ebony", "x2"...). Se usa solo para el inventario; la traducción real
la decide el pipeline, no esta heurística.
"""
import re

_EN = set("""
the of and to a in is you your it for with on that this are be as at by from or an
not have has was will can his her their they we my me our what which who when there
its into more if all but been would should could than then them these those also only
about after before over under while where how any each other some such no yes do does
""".split())
_ES = set("""
el la los las de del y que en un una es tu su sus por con para al se no lo le les
más como pero este esta estos estas ese esa eso fue ser son está están hay muy sin sobre
cuando donde quien qué cómo también todo toda todos todas otro otra mi mis nos te ya
""".split())
_ES_CHARS = re.compile(r"[áéíóúñ¿¡ü]", re.I)
_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü']+")


def classify(text: str) -> str:
    """Devuelve 'es', 'en' o 'neutral'."""
    if not text or not text.strip():
        return "neutral"
    words = [w.lower() for w in _WORD.findall(text)]
    if not words:
        return "neutral"
    en = sum(w in _EN for w in words)
    es = sum(w in _ES for w in words)
    if _ES_CHARS.search(text):
        es += 2
    if en == 0 and es == 0:
        # Textos cortos sin palabras gramaticales: nombres de objetos, lugares...
        # Si tiene varias palabras en inglés típicas de nombres, lo marcamos como 'en?'
        return "short"
    if en > es:
        return "en"
    if es > en:
        return "es"
    return "neutral"
