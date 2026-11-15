"""Lector de archivos BSA de Skyrim SE (versión 105), sin dependencias externas.

Incluye un descompresor LZ4 (formato frame) en Python puro, suficiente para
extraer archivos pequeños como las tablas de textos (.STRINGS).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

F_DIRNAMES = 0x1
F_FILENAMES = 0x2
F_COMPRESSED = 0x4
F_EMBED_NAMES = 0x100


@dataclass
class BsaFile:
    path: str      # "strings/skyrim_spanish.strings" (minúsculas, con /)
    size: int
    offset: int
    compressed: bool


class Bsa:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.files: dict[str, BsaFile] = {}
        self._read_index()

    def _read_index(self) -> None:
        with open(self.path, "rb") as f:
            hdr = f.read(36)
            magic, ver, off, aflags, nfold, nfile, lfold, lfile, _ff = struct.unpack("<4sIIIIIIIH", hdr[:34])
            if magic != b"BSA\x00" or ver not in (104, 105):
                raise ValueError(f"{self.path.name}: BSA no soportado (versión {ver})")
            self.flags = aflags
            rec = 24 if ver == 105 else 16
            folders = []
            for _ in range(nfold):
                raw = f.read(rec)
                count = struct.unpack_from("<I", raw, 8)[0]
                folders.append(count)
            entries = []
            for count in folders:
                name = ""
                if aflags & F_DIRNAMES:
                    ln = f.read(1)[0]
                    name = f.read(ln)[:-1].decode("cp1252")
                for _ in range(count):
                    _h, size, foff = struct.unpack("<QII", f.read(16))
                    entries.append((name, size, foff))
            names = f.read(lfile).split(b"\x00") if aflags & F_FILENAMES else []
        for i, (folder, size, foff) in enumerate(entries):
            fname = names[i].decode("cp1252") if i < len(names) else f"#{i}"
            p = f"{folder}/{fname}".replace("\\", "/").lower().lstrip("/")
            toggled = bool(size & 0x40000000)
            self.files[p] = BsaFile(p, size & 0x3FFFFFFF, foff,
                                    bool(aflags & F_COMPRESSED) != toggled)

    def list(self, prefix: str = "") -> list[str]:
        prefix = prefix.lower()
        return sorted(p for p in self.files if p.startswith(prefix))

    def read(self, name: str) -> bytes:
        e = self.files[name.replace("\\", "/").lower()]
        with open(self.path, "rb") as f:
            f.seek(e.offset)
            data = f.read(e.size)
        if self.flags & F_EMBED_NAMES:
            ln = data[0]
            data = data[1 + ln:]
        if not e.compressed:
            return data
        orig = struct.unpack_from("<I", data, 0)[0]
        out = lz4_frame_decompress(data[4:])
        if len(out) != orig:
            raise ValueError(f"{name}: tamaño descomprimido inesperado ({len(out)} != {orig})")
        return out


def lz4_frame_decompress(src: bytes) -> bytes:
    if struct.unpack_from("<I", src, 0)[0] != 0x184D2204:
        raise ValueError("no es un frame LZ4")
    flg = src[4]
    pos = 6
    if flg & 0x08:
        pos += 8          # tamaño del contenido
    if flg & 0x01:
        pos += 4          # id de diccionario
    pos += 1              # checksum de la cabecera
    block_checksum = bool(flg & 0x10)
    out = bytearray()
    while True:
        bsize = struct.unpack_from("<I", src, pos)[0]
        pos += 4
        if bsize == 0:
            break
        raw = bool(bsize & 0x80000000)
        bsize &= 0x7FFFFFFF
        block = src[pos:pos + bsize]
        pos += bsize + (4 if block_checksum else 0)
        if raw:
            out += block
        else:
            _lz4_block(block, out)
    return bytes(out)


def _lz4_block(src: bytes, out: bytearray) -> None:
    i, n = 0, len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        mlen = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                b = src[i]; i += 1
                mlen += b
                if b != 255:
                    break
        start = len(out) - off
        if off >= mlen:
            out += out[start:start + mlen]
        else:
            for k in range(mlen):
                out.append(out[start + k])
