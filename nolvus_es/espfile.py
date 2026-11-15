"""Lector mínimo de plugins de Skyrim SE (ESM/ESP/ESL).

Recorre todos los registros de un plugin y devuelve los textos traducibles:
nombres (FULL), descripciones (DESC), textos de libros, objetivos de misión,
líneas de diálogo, botones de mensajes, etc.

No modifica nunca el plugin: solo lee.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Qué subregistros de cada tipo de registro contienen texto visible por el jugador.
# Basado en los campos que tratan xTranslator y Dynamic String Distributor.
_FULL = {
    "ACTI", "ALCH", "AMMO", "APPA", "ARMO", "AVIF", "BOOK", "CELL", "CLAS", "CLFM",
    "CONT", "DIAL", "DOOR", "ENCH", "EXPL", "EYES", "FACT", "FLOR", "FURN", "HAZD",
    "HDPT", "INGR", "KEYM", "LCTN", "LIGH", "MESG", "MGEF", "MISC", "MSTT", "NPC_",
    "PERK", "PROJ", "QUST", "RACE", "REFR", "SCRL", "SHOU", "SLGM", "SPEL", "TACT",
    "TREE", "WATR", "WEAP", "WOOP", "WRLD",
}
TRANSLATABLE: dict[str, set[str]] = {t: {"FULL"} for t in _FULL}
_extra = {
    "AMMO": {"DESC"}, "ARMO": {"DESC"}, "AVIF": {"DESC"}, "BOOK": {"DESC", "CNAM"},
    "CLAS": {"DESC"}, "LSCR": {"DESC"}, "MESG": {"DESC", "ITXT"}, "PERK": {"DESC", "EPF2"},
    "RACE": {"DESC"}, "SCRL": {"DESC"}, "SHOU": {"DESC"}, "SPEL": {"DESC"},
    "WEAP": {"DESC"}, "MGEF": {"DNAM"}, "QUST": {"NNAM", "CNAM"},
    "ACTI": {"RNAM"}, "FLOR": {"RNAM"}, "INFO": {"NAM1", "RNAM"},
    "NPC_": {"SHRT"}, "WOOP": {"TNAM"}, "FACT": {"MNAM", "FNAM"},
}
for _t, _subs in _extra.items():
    TRANSLATABLE.setdefault(_t, set()).update(_subs)

# Campos largos (van a .DLSTRINGS / .ILSTRINGS en plugins localizados).
DL_FIELDS = {("BOOK", "DESC"), ("BOOK", "CNAM"), ("QUST", "CNAM")}
IL_FIELDS = {("INFO", "NAM1")}

FLAG_MASTER = 0x1
FLAG_LOCALIZED = 0x80
FLAG_LIGHT = 0x200
FLAG_COMPRESSED = 0x40000


@dataclass
class TextEntry:
    rec_type: str          # p.ej. "WEAP"
    form_id: int           # FormID tal como aparece en el plugin
    editor_id: str | None  # EDID, si existe
    field: str             # p.ej. "FULL"
    index: int             # posición del campo dentro del registro (para INFO NAM1, QUST NNAM...)
    text: str | None       # texto (None si el plugin está localizado y no tenemos los .STRINGS)
    string_id: int | None = None  # ID en el archivo .STRINGS si el plugin está localizado


@dataclass
class PluginInfo:
    name: str
    path: Path
    masters: list[str] = field(default_factory=list)
    localized: bool = False
    is_master: bool = False
    is_light: bool = False
    record_count: int = 0
    errors: list[str] = field(default_factory=list)


def _decode(raw: bytes) -> str:
    raw = raw.split(b"\x00", 1)[0]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _subrecords(data: bytes) -> Iterator[tuple[str, bytes]]:
    pos, n, big = 0, len(data), None
    while pos + 6 <= n:
        sig = data[pos:pos + 4].decode("latin1")
        size = struct.unpack_from("<H", data, pos + 4)[0]
        pos += 6
        if sig == "XXXX":
            big = struct.unpack_from("<I", data, pos)[0]
            pos += size
            continue
        if big is not None:
            size, big = big, None
        yield sig, data[pos:pos + size]
        pos += size


def read_header(path: Path) -> PluginInfo:
    info = PluginInfo(name=path.name, path=path)
    with open(path, "rb") as f:
        head = f.read(24)
        if len(head) < 24 or head[:4] != b"TES4":
            info.errors.append("no es un plugin TES4")
            return info
        size, flags = struct.unpack_from("<II", head, 4)
        body = f.read(size)
    info.localized = bool(flags & FLAG_LOCALIZED)
    info.is_master = bool(flags & FLAG_MASTER)
    info.is_light = bool(flags & FLAG_LIGHT)
    for sig, val in _subrecords(body):
        if sig == "MAST":
            info.masters.append(_decode(val))
    return info


def iter_texts(path: Path, strings: "StringTables | None" = None) -> tuple[PluginInfo, list[TextEntry]]:
    """Devuelve la cabecera del plugin y todos sus textos traducibles."""
    info = read_header(path)
    if info.errors:
        return info, []
    data = path.read_bytes()
    out: list[TextEntry] = []
    _walk(data, 0, len(data), info, out, strings)
    return info, out


def _walk(data: bytes, pos: int, end: int, info: PluginInfo, out: list[TextEntry], strings) -> None:
    while pos + 24 <= end:
        sig = data[pos:pos + 4]
        if sig == b"GRUP":
            gsize = struct.unpack_from("<I", data, pos + 4)[0]
            if gsize < 24:
                info.errors.append(f"GRUP corrupto en {pos}")
                return
            _walk(data, pos + 24, min(pos + gsize, end), info, out, strings)
            pos += gsize
            continue
        rtype = sig.decode("latin1")
        dsize, flags, fid = struct.unpack_from("<III", data, pos + 4)
        body = data[pos + 24:pos + 24 + dsize]
        pos += 24 + dsize
        info.record_count += 1
        wanted = TRANSLATABLE.get(rtype)
        if not wanted or rtype == "TES4":
            continue
        if flags & FLAG_COMPRESSED:
            try:
                body = zlib.decompress(body[4:])
            except zlib.error as e:
                info.errors.append(f"{rtype} {fid:08X}: no se pudo descomprimir ({e})")
                continue
        edid = None
        counters: dict[str, int] = {}
        for sub, val in _subrecords(body):
            if sub == "EDID":
                edid = _decode(val)
                continue
            if sub not in wanted:
                continue
            idx = counters.get(sub, 0)
            counters[sub] = idx + 1
            if info.localized:
                if len(val) != 4:
                    continue
                sid = struct.unpack("<I", val)[0]
                if sid == 0:
                    continue
                text = strings.get(sid, rtype, sub) if strings else None
                out.append(TextEntry(rtype, fid, edid, sub, idx, text, sid))
            else:
                text = _decode(val)
                if text.strip():
                    out.append(TextEntry(rtype, fid, edid, sub, idx, text))


class StringTables:
    """Tablas .STRINGS / .DLSTRINGS / .ILSTRINGS de un plugin localizado."""

    def __init__(self, files: dict[str, Path]):
        self.tables: dict[str, dict[int, str]] = {}
        for kind, p in files.items():
            self.tables[kind] = _read_strings(p, kind != "STRINGS")

    def get(self, sid: int, rtype: str, field_: str) -> str | None:
        if (rtype, field_) in IL_FIELDS:
            order = ("ILSTRINGS", "DLSTRINGS", "STRINGS")
        elif (rtype, field_) in DL_FIELDS or field_ in ("DESC", "CNAM"):
            order = ("DLSTRINGS", "STRINGS", "ILSTRINGS")
        else:
            order = ("STRINGS", "DLSTRINGS", "ILSTRINGS")
        for k in order:
            t = self.tables.get(k)
            if t and sid in t:
                return t[sid]
        return None


def _read_strings(path: Path, length_prefixed: bool) -> dict[int, str]:
    data = path.read_bytes()
    count, _size = struct.unpack_from("<II", data, 0)
    base = 8 + count * 8
    out = {}
    for i in range(count):
        sid, off = struct.unpack_from("<II", data, 8 + i * 8)
        p = base + off
        if length_prefixed:
            ln = struct.unpack_from("<I", data, p)[0]
            raw = data[p + 4:p + 4 + ln]
        else:
            raw = data[p:data.find(b"\x00", p)]
        out[sid] = _decode(raw)
    return out
