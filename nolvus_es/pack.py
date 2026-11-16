"""Fase 5: genera el mod "Nolvus ES - Traduccion" con todo lo traducido hasta ahora.

Fuentes (todas a la vez):
  * Español oficial de Bethesda (fase 2)            -> DSD/<maestro oficial>/nolvus-es-oficial.json
  * Traducciones importadas y traducciones con IA   -> DSD/<plugin dueño>/nolvus-es.json
  * Menús MCM                                       -> Interface/translations/<Mod>_SPANISH.txt

Se puede ejecutar en cualquier momento (también mientras la traducción va por la mitad):
solo incluye lo que ya está terminado y validado. No necesita los archivos de Nolvus,
solo la carpeta data/.

Uso:
    python -m nolvus_es.pack --data data --out "C:/Nolvus/Instances/Nolvus Awakening/MODS/mods/Nolvus ES - Traduccion"
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from .glossary import Glossary
from .style import sentence_case

DSD_DIR = Path("SKSE") / "Plugins" / "DynamicStringDistributor"
OWN_FILE = "nolvus-es.json"


def _dsd_entry(key: str, text: str, light: dict) -> tuple[str, dict]:
    owner, local, ftype, dkey = key.split("|")
    lid = int(local, 16)
    is_light = owner.lower().endswith(".esl") or light.get(owner, False)
    form_id = f"0x{lid & 0xFFF:03X}|{owner}" if is_light else f"0x{lid:06X}|{owner}"
    e = {"form_id": form_id, "type": ftype, "string": text}
    if dkey:
        if ftype == "QUST CNAM" and ":" in dkey:
            st, en = dkey.split(":")
            e["index"] = int(st) + int(en)
        else:
            e["index"] = int(dkey)
    return owner, e


def pack(data: Path, out: Path, build_official: Path | None) -> dict:
    db = sqlite3.connect(data / "trabajo.sqlite")
    meta = dict(db.execute("SELECT k, v FROM meta").fetchall())
    light = json.loads(meta.get("light_plugins", "{}"))
    mcm_files = json.loads(meta.get("mcm_files", "{}"))
    by_owner: dict[str, list] = defaultdict(list)
    mcm: dict[str, dict] = defaultdict(dict)
    stats = defaultdict(int)

    # 1. Traducciones importadas válidas (fase 3). Si dos traducciones cubren el mismo texto, gana
    #    la del catálogo revisado a mano y, después, el orden del catálogo (más texto primero).
    tm = data / "tm"
    imported_keys = set()
    prio = {}
    cat_f = Path(__file__).resolve().parent.parent / "catalogo" / "traducciones_nexus.json"
    if cat_f.exists():
        for i, a in enumerate(json.loads(cat_f.read_text(encoding="utf-8"))["archivos"]):
            prio.setdefault(f"nexus:{a['nexus']}", i)
    filas = []
    if tm.exists():
        for f in tm.glob("*.import.jsonl.gz"):
            for line in gzip.open(f, "rt", encoding="utf-8"):
                r = json.loads(line)
                if r["status"] == "ok" and not r["key"].startswith("MCM|"):
                    filas.append((prio.get(r.get("source", ""), 10 ** 6), r["key"], r["es"]))
    filas.sort()
    for _, key, es in filas:
        if key in imported_keys:
            continue
        owner, e = _dsd_entry(key, es, light)
        by_owner[owner].append(e)
        imported_keys.add(key)
        stats["importadas"] += 1
    # 2. Traducciones con IA o glosario
    gl = Glossary.load(data)
    q = """SELECT k.key, u.es, u.source, u.en FROM keys k JOIN units u ON u.uid = k.uid
           WHERE u.status = 'done' AND u.es IS NOT NULL"""
    for key, es, source, en in db.execute(q):
        if key in imported_keys:
            continue
        if source == "ia":   # mayúsculas a la española (el modelo tiende a copiar el Title Case inglés)
            fixed = sentence_case(es, en, [t["es"] for t in gl.find(en)])
            if fixed != es:
                stats["mayusculas_corregidas"] += 1
                es = fixed
        if key.startswith("MCM|"):
            _, file, k = key.split("|", 2)
            mcm[file][k] = es
            stats["mcm"] += 1
            continue
        owner, e = _dsd_entry(key, es, light)
        by_owner[owner].append(e)
        stats[source or "ia"] += 1

    # 3. Escribir (solo nuestros archivos; nunca se borra nada más del mod)
    root = out / DSD_DIR
    for owner, entries in by_owner.items():
        d = root / owner
        d.mkdir(parents=True, exist_ok=True)
        entries.sort(key=lambda e: (e["form_id"], e["type"], e.get("index", -1)))
        tmp = d / (OWN_FILE + ".tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / OWN_FILE)
    stats["plugins_con_traduccion"] = len(by_owner)
    tdir = out / "Interface" / "translations"
    for file, done in mcm.items():
        info = mcm_files.get(file)
        if not info:
            continue
        tdir.mkdir(parents=True, exist_ok=True)
        lines = [f"{k}\t{done.get(k, v)}" for k, v in info["entries"]]   # lo no traducido, en inglés
        (tdir / info["filename"]).write_text("\r\n".join(lines) + "\r\n", encoding="utf-16")
        stats["menus_mcm"] += 1
    # 4. Paquete oficial (fase 2), si se indica dónde está
    if build_official and build_official.exists():
        for f in build_official.rglob("nolvus-es-oficial.json"):
            dest = out / f.relative_to(build_official)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest)
            stats["oficial_archivos"] += 1
    meta_ini = out / "meta.ini"
    if not meta_ini.exists():
        meta_ini.write_text("[General]\ngameName=SkyrimSE\nmodid=0\nversion=0.2.0\n", encoding="utf-8")
    return dict(stats)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", required=True)
    ap.add_argument("--official", default="build/Nolvus ES", help="carpeta del paquete oficial (fase 2)")
    a = ap.parse_args(argv)
    print(json.dumps(pack(Path(a.data), Path(a.out), Path(a.official)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
