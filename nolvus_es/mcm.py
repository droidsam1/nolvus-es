"""Inventario de textos de menús (MCM) e interfaz de los mods.

Dos fuentes:
  * Interface/translations/<Mod>_<IDIOMA>.txt  (SkyUI: líneas "$CLAVE<TAB>Texto", UTF-16)
    El juego en español busca <Mod>_SPANISH.txt; si no existe, muestra las claves "$..." o el inglés.
  * MCM/Config/<Mod>/config.json (MCM Helper): textos literales que no empiezan por "$".

Uso:
    python -m nolvus_es.mcm --instance "C:/Nolvus/Instances/Nolvus Awakening" --data data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mo2 import Instance, _ci_join, _listdir


def read_translation_file(p: Path) -> dict[str, str]:
    raw = p.read_bytes()
    for enc in ("utf-16", "utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            if "$" in text:
                break
        except UnicodeDecodeError:
            continue
    out = {}
    for line in text.splitlines():
        if "\t" in line and line.startswith("$"):
            k, v = line.split("\t", 1)
            out[k.strip()] = v.rstrip("\r")
    return out


def _json_strings(obj, acc: list):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("text", "help", "valueOptions", "options", "shortNames", "displayName") or isinstance(v, (dict, list)):
                _json_strings(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _json_strings(v, acc)
    elif isinstance(obj, str) and obj and not obj.startswith("$") and any(c.isalpha() for c in obj):
        acc.append(obj)


def scan(inst: Instance) -> dict:
    files: dict[str, dict] = {}       # nombre base (minúsculas) -> {idioma: (mod, ruta)}
    mcm_json = []
    for mod in inst.enabled_mods():      # de menor a mayor prioridad: el último gana
        base = inst.mods_dir / mod
        tdir = _ci_join(base, ["Interface", "translations"])
        if tdir:
            for name in _listdir(str(tdir)):
                if not name.lower().endswith(".txt") or "_" not in name:
                    continue
                stem, lang = name[:-4].rsplit("_", 1)
                files.setdefault(stem.lower(), {})[lang.lower()] = (mod, str(tdir / name))
        cdir = _ci_join(base, ["MCM", "Config"])
        if cdir:
            for sub in _listdir(str(cdir)):
                cfg = _ci_join(cdir, [sub, "config.json"])
                if cfg:
                    mcm_json.append((mod, sub, str(cfg)))
    rows = []
    for stem, langs in sorted(files.items()):
        en = langs.get("english")
        if not en:
            continue
        try:
            n = len(read_translation_file(Path(en[1])))
        except OSError:
            n = -1
        real_es = 0
        if "spanish" in langs and n > 0:
            try:
                e_map = read_translation_file(Path(en[1]))
                s_map = read_translation_file(Path(langs["spanish"][1]))
                real_es = sum(1 for k, v in e_map.items() if k in s_map and s_map[k] != v)
            except OSError:
                pass
        rows.append({"file": stem, "mod": en[0], "keys": n, "has_spanish": "spanish" in langs,
                     # Muchos mods incluyen un _SPANISH.txt que es copia literal del inglés
                     "spanish_is_real": real_es >= max(1, n * 0.3),
                     "path_english": en[1]})
    js = []
    for mod, sub, cfg in mcm_json:
        acc: list = []
        try:
            _json_strings(json.loads(Path(cfg).read_text(encoding="utf-8-sig")), acc)
        except (OSError, ValueError):
            pass
        js.append({"mod": mod, "config": sub, "literal_strings": len(acc), "path": cfg})
    return {"translations": rows, "mcm_helper": js}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--profile", default="Nolvus Awakening")
    ap.add_argument("--data", default="data")
    a = ap.parse_args(argv)
    r = scan(Instance(Path(a.instance), a.profile))
    Path(a.data, "mcm_inventory.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    t = r["translations"]
    print(json.dumps({
        "archivos_traduccion_ingles": len(t),
        "con_archivo_spanish": sum(x["has_spanish"] for x in t),
        "realmente_en_espanol": sum(x["spanish_is_real"] for x in t),
        "claves_por_traducir": sum(x["keys"] for x in t if not x["spanish_is_real"] and x["keys"] > 0),
        "configs_mcm_helper": len(r["mcm_helper"]),
        "textos_literales_mcm_helper": sum(x["literal_strings"] for x in r["mcm_helper"]),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
