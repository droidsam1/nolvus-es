"""Textos oficiales de Bethesda (inglés y español) de los maestros localizados.

Para cada plugin oficial (Skyrim.esm, Update.esm, DLC y Creation Club) lee los
registros y busca sus textos en las tablas .STRINGS en inglés y en español que
vienen dentro de los BSA del juego.

Resultado: clave -> (texto_en, texto_es), donde la clave identifica el campo
igual que lo hace Dynamic String Distributor:
    (plugin_dueño, formid_local, "TIPO CAMPO", indice_dsd)
"""
from __future__ import annotations

import gzip
import json
import struct
from pathlib import Path

from .bsa import Bsa
from .espfile import TextEntry, _read_strings_bytes, iter_texts, read_header

OFFICIAL_MASTERS = ("Skyrim.esm", "Update.esm", "Dawnguard.esm", "HearthFires.esm", "Dragonborn.esm")


def local_id(fid: int, owner_is_light: bool) -> int:
    return fid & (0xFFF if owner_is_light else 0xFFFFFF)


def owner_of(fid: int, masters: list[str], self_name: str) -> str:
    i = fid >> 24
    return masters[i] if i < len(masters) else self_name


def dsd_index_key(e) -> str:
    d = e["di"] if isinstance(e, dict) else e.dsd_index
    if d is None:
        return ""
    if isinstance(d, (list, tuple)):
        return f"{d[0]}:{d[1]}"
    return str(d)


def _tables(bsa: Bsa, stem: str, lang: str) -> dict[str, dict[int, str]]:
    out = {}
    for kind in ("strings", "dlstrings", "ilstrings"):
        name = f"strings/{stem.lower()}_{lang}.{kind}"
        if name in bsa.files:
            out[kind.upper()] = _read_strings_bytes(bsa.read(name), kind != "strings")
    return out


def _lookup(tables, sid: int, rtype: str, field: str) -> str | None:
    if (rtype, field) == ("INFO", "NAM1"):
        order = ("ILSTRINGS", "DLSTRINGS", "STRINGS")
    elif field in ("DESC", "CNAM"):
        order = ("DLSTRINGS", "STRINGS", "ILSTRINGS")
    else:
        order = ("STRINGS", "DLSTRINGS", "ILSTRINGS")
    for k in order:
        t = tables.get(k)
        if t and sid in t:
            return t[sid]
    return None


def build(data_dir: Path, plugins: list[str], out_file: Path) -> dict:
    """Construye el diccionario oficial EN/ES para los plugins oficiales dados (en orden de carga)."""
    iface = None
    result: dict[str, list] = {}
    stats = {}
    for name in plugins:
        path = data_dir / name
        if not path.exists():
            continue
        stem = path.stem
        bsa = None
        if name in OFFICIAL_MASTERS:
            iface = iface or Bsa(data_dir / "Skyrim - Interface.bsa")
            bsa = iface
        if bsa is None:
            bp = data_dir / f"{stem}.bsa"
            if not bp.exists():
                stats[name] = "sin BSA"
                continue
            bsa = Bsa(bp)
        en, es = _tables(bsa, stem, "english"), _tables(bsa, stem, "spanish")
        info, entries = iter_texts(path, None)
        if not info.localized:
            stats[name] = "no localizado"
            continue
        n = 0
        for e in entries:
            owner = owner_of(e.form_id, info.masters, name)
            owner_light = owner.lower().endswith(".esl")
            key = f"{owner}|{local_id(e.form_id, owner_light):06X}|{e.rec_type} {e.field}|{dsd_index_key(e)}"
            ten = _lookup(en, e.string_id, e.rec_type, e.field)
            tes = _lookup(es, e.string_id, e.rec_type, e.field)
            if ten is None and tes is None:
                continue
            result[key] = [ten, tes, e.editor_id]   # los posteriores (Update.esm...) sobrescriben
            n += 1
        stats[name] = n
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_file, "wt", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    return stats
