"""Fase 2: recuperar el español oficial para registros del juego base que los mods dejan en inglés.

Para cada campo de texto de un registro oficial (Skyrim.esm, DLC, Creation Club) se
mira qué plugin "gana" (el último en el orden de carga que lo sobrescribe) y:

  * si su texto coincide con el inglés oficial  -> se usa el español oficial (exacto);
  * si ya está en español                        -> no se toca;
  * si el mod cambió el texto                    -> va a la cola de traducción con IA,
    guardando el español oficial como referencia de estilo y terminología.

Uso:
    python -m nolvus_es.phase2 --data data --build "build/Nolvus ES"
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from .inventory import OFFICIAL
from .lang import classify

PACK_NAME = "nolvus-es-oficial.json"


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-").replace("…", "...")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def norm_alnum(s: str | None) -> str:
    """Solo letras y números: ignora puntuación, espacios y etiquetas de formato."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"[\W_]+", "", norm(s))


def dsd_index(field_type: str, di) -> int | None:
    if di is None:
        return None
    if field_type == "QUST CNAM":          # etapa + nº de entrada del diario (como DSD)
        return int(di[0]) + int(di[1])
    return int(di)


def run(data: Path, build: Path) -> dict:
    official = json.load(gzip.open(data / "official.json.gz", "rt", encoding="utf-8"))
    state = json.loads((data / "plugins.json").read_text(encoding="utf-8"))

    # 1. Quién gana cada campo de un registro oficial (último en el orden de carga).
    winner: dict[str, tuple[str, dict]] = {}
    for p in state["plugins"]:
        s = p.get("summary") or {}
        if s.get("official") or s.get("error") or not p.get("done"):
            continue
        f = data / "extract" / f'{p["name"]}.jsonl.gz'
        if not f.exists():
            continue
        masters = s.get("masters", [])
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                i = r["fid"] >> 24
                owner = masters[i] if i < len(masters) else p["name"]
                if not OFFICIAL.match(owner):
                    continue
                local = r["fid"] & (0xFFF if owner.lower().endswith(".esl") else 0xFFFFFF)
                di = r.get("di")
                dkey = "" if di is None else (f"{di[0]}:{di[1]}" if isinstance(di, list) else str(di))
                key = f'{owner}|{local:06X}|{r["t"]} {r["f"]}|{dkey}'
                winner[key] = (p["name"], r)

    # 2. Decidir qué hacer con cada campo.
    stats = Counter()
    by_owner: dict[str, list] = defaultdict(list)
    queue = []
    for key, (plugin, r) in winner.items():
        owner, local, ftype, _ = key.split("|")
        text = r["s"]
        off = official.get(key)
        if text is None:
            stats["sin_texto (plugin localizado)"] += 1
            continue
        if off and norm(text) == norm(off[1]):
            stats["ya_en_espanol_oficial"] += 1
            continue
        if off and (norm(text) == norm(off[0]) or norm_alnum(text) == norm_alnum(off[0])):
            entry = {"form_id": f"0x{local}|{owner}", "type": ftype, "string": off[1]}
            idx = dsd_index(ftype, r.get("di"))
            if idx is not None:
                entry["index"] = idx
            by_owner[owner].append(entry)
            stats["resuelto_con_oficial"] += 1
            continue
        if classify(text) == "es":
            stats["ya_en_espanol_mod"] += 1
            continue
        queue.append({"key": key, "plugin": plugin, "edid": r.get("edid"), "en": text,
                      "ref_en": off[0] if off else None, "ref_es": off[1] if off else None})
        stats["cola_ia_texto_cambiado" if off else "cola_ia_campo_nuevo"] += 1

    # 3. Escribir el paquete DSD.
    root = build / "SKSE" / "Plugins" / "DynamicStringDistributor"
    for owner, entries in by_owner.items():
        d = root / owner
        d.mkdir(parents=True, exist_ok=True)
        entries.sort(key=lambda e: (e["form_id"], e["type"], e.get("index", -1)))
        (d / PACK_NAME).write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    with gzip.open(data / "queue_vanilla_changed.jsonl.gz", "wt", encoding="utf-8") as f:
        for q in queue:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    stats["plugins_dueños"] = len(by_owner)
    return dict(stats)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--build", default="build/Nolvus ES")
    a = ap.parse_args(argv)
    print(json.dumps(run(Path(a.data), Path(a.build)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
