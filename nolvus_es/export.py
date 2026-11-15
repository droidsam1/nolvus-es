"""Exporta las traducciones del proyecto a la carpeta traducciones/ del repositorio.

Un archivo por plugin: traducciones/<plugin>.jsonl, una línea por texto, ordenadas por clave
(así los cambios se ven bien en git y se pueden corregir a mano o con un pull request):

    {"k": "<dueño>|<FormID>|<TIPO CAMPO>|<índice DSD>", "h": "<huella del inglés>", "es": "<español>"}

  * k  -> qué texto es (la misma clave que usa Dynamic String Distributor).
  * h  -> huella (sha1, 12 caracteres) del texto inglés que se tradujo. Al instalar solo se aplica
          si el texto del mod del usuario tiene la misma huella: si el mod se actualiza y cambia
          el texto, la traducción vieja no se usa por error.
  * es -> la traducción.

No se exporta el texto inglés original (es de los autores de cada mod) ni nada importado de las
traducciones de Nexus: solo lo traducido por el proyecto (IA y glosario oficial).

Las correcciones hechas a mano en estos archivos se conservan: si una línea ya existe con la
misma clave y huella, export no la pisa (se marca con "manual": true al corregirla).

Uso:
    python -m nolvus_es.export --data data --out traducciones
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from .glossary import Glossary
from .style import sentence_case


def huella(en: str) -> str:
    return hashlib.sha1(en.strip().encode("utf-8")).hexdigest()[:12]


def safe_name(plugin: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", plugin)


def _read(path: Path) -> dict[str, dict]:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["k"]] = r
    return out


def export(data: Path, out: Path) -> dict:
    db = sqlite3.connect(f"file:{data / 'trabajo.sqlite'}?mode=ro", uri=True)
    gl = Glossary.load(data)
    by_plugin: dict[str, dict[str, dict]] = defaultdict(dict)
    stats = defaultdict(int)
    q = """SELECT k.key, k.plugin, u.en, u.es, u.source FROM keys k JOIN units u ON u.uid = k.uid
           WHERE u.status = 'done' AND u.es IS NOT NULL AND u.source IN ('ia', 'glosario')"""
    for key, plugin, en, es, source in db.execute(q):
        if source == "ia":
            es = sentence_case(es, en, [t["es"] for t in gl.find(en)])
        by_plugin[plugin][key] = {"k": key, "h": huella(en), "es": es}
        stats[source] += 1
    out.mkdir(parents=True, exist_ok=True)
    for plugin, rows in by_plugin.items():
        f = out / f"{safe_name(plugin)}.jsonl"
        old = _read(f)
        for k, r in old.items():           # correcciones manuales: se respetan mientras el inglés no cambie
            if r.get("manual") and (k not in rows or rows[k]["h"] == r["h"]):
                rows[k] = r
                stats["manuales_conservadas"] += 1
        text = "".join(json.dumps(rows[k], ensure_ascii=False) + "\n" for k in sorted(rows))
        if not f.exists() or f.read_text(encoding="utf-8") != text:
            f.write_text(text, encoding="utf-8", newline="\n")
            stats["archivos_cambiados"] += 1
    stats["plugins"] = len(by_plugin)
    return dict(stats)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="traducciones")
    a = ap.parse_args(argv)
    print(json.dumps(export(Path(a.data), Path(a.out)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
