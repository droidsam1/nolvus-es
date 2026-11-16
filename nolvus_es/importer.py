"""Fase 3: importar traducciones al español ya publicadas (plugins traducidos) a la memoria de traducción.

Empareja cada registro del plugin traducido con el plugin ORIGINAL instalado en Nolvus:

  * misma clave (dueño | FormID | tipo campo | índice DSD)
  * y misma huella de todo lo que no es texto en ese registro
      -> "ok": la traducción corresponde a tu versión del mod y se usa tal cual.
  * huella distinta (la traducción es de otra versión del mod)
      -> "referencia": no se usa directamente; la IA la tendrá como guía.

Uso:
    python -m nolvus_es.importer --data data --original "ruta/Mod.esp" --translated "ruta/Mod_ES.esp" --source "nexus:56508"
    python -m nolvus_es.importer --data data --scan-mods "C:/Nolvus/Instances/Nolvus Awakening/MODS/mods" --sources sources.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from collections import Counter
from pathlib import Path

from .espfile import iter_texts
from .lang import classify
from .official import dsd_index_key, owner_of


def _key(e, masters, self_name) -> str:
    owner = owner_of(e.form_id, masters, self_name)
    local = e.form_id & (0xFFF if owner.lower().endswith(".esl") else 0xFFFFFF)
    return f"{owner}|{local:06X}|{e.rec_type} {e.field}|{dsd_index_key(e)}"


def import_pair(original: Path, translated: Path, source: str, tm_dir: Path) -> dict:
    oinfo, oent = iter_texts(original, hashes=True)
    tinfo, tent = iter_texts(translated, hashes=True)
    name = original.name
    orig = {}
    for e in oent:
        orig[_key(e, oinfo.masters, name)] = (e, oinfo.rec_hash.get(e.form_id))
    stats = Counter()
    out = []
    for e in tent:
        k = _key(e, tinfo.masters, name)
        o = orig.get(k)
        if o is None:
            stats["sin_pareja_en_original"] += 1
            continue
        oe, ohash = o
        if not e.text or not oe.text or e.text.strip() == oe.text.strip():
            stats["sin_traducir"] += 1
            continue
        if classify(e.text) == "en":
            stats["parece_ingles"] += 1
            continue
        same = ohash is not None and tinfo.rec_hash.get(e.form_id) == ohash
        status = "ok" if same else "referencia"
        stats[status] += 1
        out.append({"key": k, "plugin": name, "en": oe.text, "es": e.text, "status": status,
                    "source": source, "edid": oe.editor_id})
    tm_dir.mkdir(parents=True, exist_ok=True)
    # Un archivo por plugin y fuente: dos traducciones del mismo mod no se pisan
    tag = "".join(c if c.isalnum() else "_" for c in source)
    with gzip.open(tm_dir / f"{name}.{tag}.import.jsonl.gz", "wt", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    stats["textos_original"] = len(oent)
    return dict(stats)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--original")
    ap.add_argument("--translated")
    ap.add_argument("--source", default="manual")
    ap.add_argument("--sources", help="JSON: lista de {plugin, translated, source}")
    a = ap.parse_args(argv)
    tm = Path(a.data) / "tm"
    state = json.loads((Path(a.data) / "plugins.json").read_text(encoding="utf-8"))
    paths = {p["name"].lower(): p["path"] for p in state["plugins"] if p.get("path")}
    jobs = []
    if a.sources:
        jobs = json.loads(Path(a.sources).read_text(encoding="utf-8"))
    elif a.original and a.translated:
        jobs = [{"plugin": Path(a.original).name, "original": a.original, "translated": a.translated, "source": a.source}]
    report = {}
    for j in jobs:
        orig = j.get("original") or paths.get(j["plugin"].lower())
        if not orig:
            report[j["plugin"]] = {"error": "plugin no activo en Nolvus"}
            continue
        t0 = time.time()
        r = import_pair(Path(orig), Path(j["translated"]), j.get("source", "?"), tm)
        r["segundos"] = round(time.time() - t0, 1)
        report[j["plugin"]] = r
        print(j["plugin"], json.dumps(r, ensure_ascii=False), flush=True)
    (Path(a.data) / "import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
