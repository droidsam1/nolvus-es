"""Descomprime las traducciones descargadas de Nexus en data/imports/<id de Nexus>/<archivo>/.

Reconoce cada archivo por el ID de Nexus que lleva en el nombre (p. ej. "...-56508-4-53-...7z").
Usa el 7-Zip que trae Nolvus (abre .7z, .rar y .zip). Idempotente: lo ya extraído se salta.

Uso (en Windows):
    python -m nolvus_es.extract --downloads "%USERPROFILE%/Downloads" --data data
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# Traducciones de docs/TRADUCCIONES.md (+ DSD)
KNOWN = {
    "56508": "Interesting NPCs", "20416": "Legacy of the Dragonborn", "40020": "Beyond Skyrim Bruma",
    "99307": "Remiel", "169755": "Inigo", "67225": "Vigilant", "151442": "Katana", "11547": "Falskaar",
    "31886": "Lucien", "45596": "Wyrmstooth", "87636": "BS Bruma - LOTD Synergy", "21283": "The Forgotten City",
    "57613": "Unslaad - LOTD patch", "67222": "Unslaad", "163778": "Vigilant - Book Covers",
    "125480": "The Wheels of Lull", "3472": "Ordinator", "32849": "Carved Brink", "57186": "Thaumaturgy",
    "125343": "Clockwork", "178421": "Auri", "22563": "Wintersun", "107676": "DSD",
}
ARCHIVE_EXT = (".7z", ".rar", ".zip")
SEVEN_ZIP = [Path(r"C:\Nolvus\lib\7z.exe"), Path(r"C:\Program Files\7-Zip\7z.exe")]


def nexus_id(name: str) -> str | None:
    for m in re.finditer(r"(?<![0-9])(\d{3,6})(?![0-9])", name):
        if m.group(1) in KNOWN:
            return m.group(1)
    return None


def _seven_zip() -> str | None:
    for p in SEVEN_ZIP:
        if p.exists():
            return str(p)
    return shutil.which("7z")


def extract_all(downloads: Path, data: Path) -> list[dict]:
    out = []
    sz = _seven_zip()
    for f in sorted(downloads.iterdir()):
        if not f.is_file() or not f.name.lower().endswith(ARCHIVE_EXT):
            continue
        nid = nexus_id(f.name)
        if not nid:
            continue
        dest = data / "imports" / nid / f.stem
        marker = dest / ".extraido"
        row = {"archivo": f.name, "nexus": nid, "mod": KNOWN[nid], "destino": str(dest)}
        if marker.exists():
            row["estado"] = "ya extraído"
            out.append(row)
            continue
        dest.mkdir(parents=True, exist_ok=True)
        try:
            if f.suffix.lower() == ".zip":
                with zipfile.ZipFile(f) as z:
                    z.extractall(dest)
            elif sz:
                r = subprocess.run([sz, "x", "-y", f"-o{dest}", str(f)], capture_output=True, text=True)
                if r.returncode != 0:
                    raise RuntimeError(r.stderr.strip()[-300:] or r.stdout.strip()[-300:])
            else:
                raise RuntimeError("no encuentro 7-Zip (C:\\Nolvus\\lib\\7z.exe)")
            marker.write_text(f.name, encoding="utf-8")
            row["estado"] = "extraído"
        except Exception as e:  # noqa: BLE001
            row["estado"] = f"ERROR: {e}"
        out.append(row)
    (data / "imports").mkdir(parents=True, exist_ok=True)
    (data / "imports" / "extraccion.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--downloads", required=True)
    ap.add_argument("--data", default="data")
    a = ap.parse_args(argv)
    rows = extract_all(Path(a.downloads), Path(a.data))
    for r in rows:
        print(f'{r["estado"]:<14} {r["mod"]:<28} {r["archivo"]}')
    falta = sorted(set(KNOWN) - {r["nexus"] for r in rows})
    print(f"\n{len(rows)} archivos reconocidos. Sin descargar todavía: " + ", ".join(KNOWN[i] for i in falta))


if __name__ == "__main__":
    main()
