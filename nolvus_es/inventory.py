"""Paso 1: inventario de todos los textos traducibles de una instancia de Nolvus.

Uso:
    python -m nolvus_es.inventory extract --instance "C:/Nolvus/Instances/Nolvus Awakening" --out data [--budget 150]
    python -m nolvus_es.inventory report --out data

`extract` es reanudable: procesa plugins hasta agotar el tiempo (--budget, en segundos)
y la siguiente ejecución continúa donde se quedó. Nunca modifica nada de Nolvus.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from .espfile import StringTables, iter_texts, read_header
from .lang import classify
from .mo2 import Instance

OFFICIAL = re.compile(r"^(skyrim\.esm|update\.esm|dawnguard\.esm|hearthfires\.esm|dragonborn\.esm|cc[a-z]{3}sse\d{3}-[a-z0-9_]+\.es[lm]|_resourcepack\.esl)$", re.I)


def _string_files(inst: Instance, plugin: str) -> tuple[dict[str, Path], str | None]:
    stem = Path(plugin).stem
    for lang in ("spanish", "english"):
        files = {}
        for kind in ("STRINGS", "DLSTRINGS", "ILSTRINGS"):
            p = inst.find_loose_file(f"Strings/{stem}_{lang}.{kind}")
            if p:
                files[kind] = p
        if files:
            return files, lang
    return {}, None


def _save(state_file: Path, state: dict) -> None:
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(state_file)


def extract(args) -> None:
    inst = Instance(Path(args.instance), args.profile)
    out = Path(args.out)
    (out / "extract").mkdir(parents=True, exist_ok=True)
    state_file = out / "plugins.json"
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
    else:
        resolved = inst.resolve_plugins()
        order = inst.active_plugins()
        state = {"plugins": []}
        for i, name in enumerate(order):
            path, mod = resolved.get(name.lower(), (None, None))
            state["plugins"].append({"load_index": i, "name": name, "path": str(path) if path else None,
                                     "mod": mod, "done": False})
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(order)} plugins activos; resueltos {sum(1 for p in state['plugins'] if p['path'])}")

    t0 = time.time()
    done_now = 0
    for p in state["plugins"]:
        if p["done"]:
            continue
        if time.time() - t0 > args.budget:
            break
        name = p["name"]
        summary = {"official": bool(OFFICIAL.match(name))}
        if not p["path"]:
            summary["error"] = "no encontrado en los mods activos"
        elif summary["official"]:
            hdr = read_header(Path(p["path"]))
            summary.update(localized=hdr.localized, masters=hdr.masters)
        else:
            path = Path(p["path"])
            hdr = read_header(path)
            strings, slang = (None, None)
            if hdr.localized:
                files, slang = _string_files(inst, name)
                strings = StringTables(files) if files else None
            info, entries = iter_texts(path, strings)
            counts = Counter()
            words = Counter()
            with gzip.open(out / "extract" / f"{name}.jsonl.gz", "wt", encoding="utf-8") as f:
                for e in entries:
                    lang = classify(e.text) if e.text is not None else "unknown"
                    counts[lang] += 1
                    words[lang] += len(e.text.split()) if e.text else 0
                    f.write(json.dumps({"t": e.rec_type, "fid": e.form_id, "edid": e.editor_id,
                                        "f": e.field, "i": e.index, "di": e.dsd_index,
                                        "s": e.text, "sid": e.string_id,
                                        "lang": lang}, ensure_ascii=False) + "\n")
            summary.update(localized=info.localized, strings_lang=slang, masters=info.masters,
                           is_light=info.is_light, records=info.record_count,
                           entries=len(entries), by_lang=dict(counts), words=dict(words),
                           errors=info.errors[:5])
        p.update(done=True, summary=summary)
        done_now += 1
        if done_now % 25 == 0:
            _save(state_file, state)
            print(f"  {done_now} plugins ({time.time() - t0:.0f}s) ultimo: {name}", flush=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    _save(state_file, state)
    left = sum(1 for p in state["plugins"] if not p["done"])
    print(f"procesados ahora: {done_now}; pendientes: {left}; {time.time() - t0:.0f}s")


def report(args) -> None:
    out = Path(args.out)
    state = json.loads((out / "plugins.json").read_text(encoding="utf-8"))
    tot = Counter(); words = Counter(); by_field = Counter(); per_mod = defaultdict(Counter)
    localized_missing, errors, official = [], [], 0
    for p in state["plugins"]:
        s = p.get("summary") or {}
        if s.get("official"):
            official += 1
            continue
        if s.get("error"):
            errors.append((p["name"], s["error"]))
            continue
        tot.update(s.get("by_lang", {}))
        words.update(s.get("words", {}))
        if s.get("localized") and not s.get("strings_lang"):
            localized_missing.append(p["name"])
        per_mod[p["mod"]]["en"] += s.get("by_lang", {}).get("en", 0) + s.get("by_lang", {}).get("short", 0)
        per_mod[p["mod"]]["words"] += s.get("words", {}).get("en", 0) + s.get("words", {}).get("short", 0)
    for f in (out / "extract").glob("*.jsonl.gz"):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r["lang"] in ("en", "short"):
                    by_field[f'{r["t"]} {r["f"]}'] += 1
    rep = {
        "plugins_total": len(state["plugins"]),
        "plugins_oficiales_bethesda": official,
        "textos_por_idioma": dict(tot),
        "palabras_por_idioma": dict(words),
        "plugins_localizados_sin_strings_sueltos": localized_missing,
        "errores": errors,
        "top_tipos_en_ingles": by_field.most_common(25),
        "top_mods_en_ingles": sorted(((m, c["en"], c["words"]) for m, c in per_mod.items()),
                                     key=lambda x: -x[2])[:40],
    }
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k not in ("top_mods_en_ingles",)}, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--instance", required=True)
    e.add_argument("--profile", default="Nolvus Awakening")
    e.add_argument("--out", default="data")
    e.add_argument("--budget", type=float, default=150)
    r = sub.add_parser("report")
    r.add_argument("--out", default="data")
    a = ap.parse_args(argv)
    {"extract": extract, "report": report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
