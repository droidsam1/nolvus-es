"""Protección y validación de marcadores en los textos de Skyrim.

Antes de traducir, cada marcador se sustituye por una ficha numerada (⟦1⟧, ⟦2⟧...) para
que el traductor no pueda alterarlo; después se restauran. Al final, `validate` comprueba
que la traducción no ha perdido, duplicado ni inventado nada.

Marcadores que se protegen:
  - Etiquetas entre < >: <mag>, <dur>, <15>, <Alias=Player>, <Alias.ShortName=X>, <Global=Y>,
    HTML de libros (<font face="$HandwrittenFont">, </p>, <br>, <img src='...'>...)
  - [PageBreak] de los libros
  - Formatos de cadena: %s %d %i %.0f %%  y {0} {1}
  - Saltos de línea (se cuentan, no se enmascaran)
"""
from __future__ import annotations

import re
from collections import Counter

TOKEN_RE = re.compile(
    r"<[^<>\n]{1,200}>"              # etiquetas y variables del juego
    r"|\[pagebreak\]"                # salto de página de libros
    r"|%(?:\d+\$)?[-+#0]*\d*(?:\.\d+)?[sdifxXc](?![A-Za-zÁÉÍÓÚÑáéíóúñ])"  # formatos printf (%s, %d, %.0f)
    r"|\{\d+\}",                      # formatos {0}
    re.I,
)
SLOT_RE = re.compile(r"⟦(\d+)⟧")
_LETTERS = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]")


def protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(m):
        tokens.append(m.group(0))
        return f"⟦{len(tokens)}⟧"

    return TOKEN_RE.sub(repl, text), tokens


def restore(text: str, tokens: list[str]) -> str:
    def repl(m):
        i = int(m.group(1))
        return tokens[i - 1] if 1 <= i <= len(tokens) else m.group(0)

    return SLOT_RE.sub(repl, text)


def validate(src: str, dst: str) -> list[str]:
    """Errores que impiden usar la traducción (lista vacía = válida)."""
    errors = []
    has_text = bool(_LETTERS.search(src))
    if not dst or not dst.strip():
        return ["traducción vacía"] if has_text else []
    if SLOT_RE.search(dst):
        errors.append("quedan fichas ⟦n⟧ sin restaurar")
    s_tok = Counter(t.lower() for t in TOKEN_RE.findall(src))
    d_tok = Counter(t.lower() for t in TOKEN_RE.findall(dst))
    if s_tok != d_tok:
        lost, extra = s_tok - d_tok, d_tok - s_tok
        if lost:
            errors.append(f"marcadores perdidos: {sorted(lost)}")
        if extra:
            errors.append(f"marcadores añadidos: {sorted(extra)}")
    if has_text and not _LETTERS.search(dst):
        errors.append("la traducción no tiene texto")
    return errors


def warnings(src: str, dst: str) -> list[str]:
    """Avisos para revisión: no bloquean, pero conviene mirarlos."""
    out = []
    si, di = src.strip().count("\n"), dst.strip().count("\n")
    if si != di:
        out.append(f"saltos de línea internos distintos ({si} -> {di})")
    s_len = len(TOKEN_RE.sub("", src).strip())
    d_len = len(TOKEN_RE.sub("", dst).strip())
    if s_len >= 40 and not (0.45 <= d_len / max(s_len, 1) <= 2.5):
        out.append(f"longitud sospechosa ({s_len} -> {d_len} caracteres)")
    return out
