"""Ajustes de estilo deterministas que se aplican al empaquetar.

sentence_case: el inglés de los menús y nombres usa "Title Case" ("Max Widget Size");
en español solo va mayúscula la primera palabra y los nombres propios
("Tamaño máximo del widget"). Los modelos pequeños tienden a copiar el estilo inglés,
así que se corrige aquí, sin volver a traducir.
"""
from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü][A-Za-zÁÉÍÓÚÑÜáéíóúñü'\-]*")
_SMALL_EN = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "by", "with", "from", "vs"}


def is_title_case(en: str) -> bool:
    words = [w for w in _WORD.findall(re.sub(r"<[^>]*>", " ", en))]
    big = [w for w in words if w.lower() not in _SMALL_EN]
    if len(big) < 2:
        return False
    return sum(w[:1].isupper() for w in big) / len(big) >= 0.8


def sentence_case(es: str, en: str, keep_terms: list[str]) -> str:
    """Pone en minúscula las palabras con mayúscula 'inglesa', respetando nombres propios."""
    if not is_title_case(en):
        return es
    en_words = set()
    for w in _WORD.findall(en):              # "Inigo's" cuenta también como "Inigo"
        en_words.add(w)
        en_words.update(p for p in re.split(r"['\-]", w) if p)
    keep = set()
    for t in keep_terms:                      # términos del glosario (p. ej. "Carrera Blanca")
        keep.update(_WORD.findall(t))
    out, first, i = [], True, 0
    for m in _WORD.finditer(es):
        w = m.group(0)
        out.append(es[i:m.start()])
        before = es[max(0, m.start() - 2):m.start()]
        sentence_start = first or re.search(r"[.!?¿¡]\s*$", before)
        if (sentence_start or w in keep or w in en_words or w.isupper() or any(c.isdigit() for c in w)
                or not w[:1].isupper()):
            out.append(w)
        else:
            out.append(w[:1].lower() + w[1:])
        first = False
        i = m.end()
    out.append(es[i:])
    return "".join(out)
