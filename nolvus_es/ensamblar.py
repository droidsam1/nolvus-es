"""Ensambla el mod "Nolvus ES - Traduccion" en el PC del jugador, sin IA.

Fuentes, de más a menos prioridad para un mismo texto:
  1. Traducciones de Nexus que el jugador ha descargado (data/tm/*.import.jsonl.gz, estado "ok":
     comprobadas registro a registro contra SU versión de cada mod).
  2. Traducciones del proyecto (traducciones/*.jsonl): solo se aplican si la huella del texto
     inglés coincide con el texto que tiene ahora mismo el mod del jugador.
  3. Español oficial de Bethesda (fase 2, generado a partir de su propio juego).

Necesita haber pasado antes el inventario (data/plugins.json + data/extract) y el escaneo de
menús (data/mcm_inventory.json) sobre la instalación del jugador.
"""
from __future__ import annotations

import gzip
import json
import shutil
from collections import defaultdict
from pathlib import Path

from .export import huella
from .inventory import OFFICIAL
from .mcm import read_translation_file
from .pack import DSD_DIR, OWN_FILE, _dsd_entry


def textos_actuales(data: Path) -> tuple[dict[str, str], dict[str, bool]]:
    """clave -> texto inglés que gana en la instalación del jugador; y qué plugins son ligeros (ESL)."""
    state = json.loads((data / "plugins.json").read_text(encoding="utf-8"))
    light = {p["name"]: bool((p.get("summary") or {}).get("is_light")) for p in state["plugins"]}
    winner: dict[str, str] = {}
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
                if r["s"] is None:
                    continue
                i = r["fid"] >> 24
                owner = masters[i] if i < len(masters) else p["name"]
                official = bool(OFFICIAL.match(owner))
                local = r["fid"] & (0xFFF if official and owner.lower().endswith(".esl") else 0xFFFFFF)
                di = r.get("di")
                dkey = "" if di is None else (f"{di[0]}:{di[1]}" if isinstance(di, list) else str(di))
                winner[f'{owner}|{local:06X}|{r["t"]} {r["f"]}|{dkey}'] = r["s"]
    return winner, light


def ensamblar(data: Path, traducciones: Path, out: Path, oficial: Path | None, light: dict | None = None) -> dict:
    """light: {plugin: es ESL}. Si no se da, se saca del inventario (data/plugins.json)."""
    stats = defaultdict(int)
    propias = sorted(traducciones.glob("*.jsonl")) if traducciones.exists() else []
    if propias and not (data / "plugins.json").exists():
        propias = []                      # sin inventario no se pueden comprobar: no se usan
        stats["traducciones_propias_sin_inventario"] = 1
    actual = {}
    if propias or light is None:          # el inventario completo solo hace falta para traducciones propias
        actual, light_inv = textos_actuales(data)
        light = light if light is not None else light_inv
    by_owner: dict[str, dict[tuple, dict]] = defaultdict(dict)
    hechas: set[str] = set()

    def add(key: str, es: str, fuente: str):
        owner, e = _dsd_entry(key, es, light)
        by_owner[owner][(e["form_id"], e["type"], e.get("index", -1))] = e
        hechas.add(key)
        stats[fuente] += 1

    # 1. Traducciones de Nexus descargadas por el jugador
    tm = data / "tm"
    for f in sorted(tm.glob("*.import.jsonl.gz")) if tm.exists() else []:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r["status"] == "ok" and not r["key"].startswith("MCM|"):
                    add(r["key"], r["es"], "nexus")

    # 2. Traducciones del proyecto
    mcm_inv = {}
    mi = data / "mcm_inventory.json"
    if mi.exists():
        for t in json.loads(mi.read_text(encoding="utf-8"))["translations"]:
            if not t.get("spanish_is_real"):
                mcm_inv[t["file"]] = t
    mcm_en: dict[str, dict] = {}
    mcm_es: dict[str, dict] = defaultdict(dict)
    for f in propias:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            k = r["k"]
            if k.startswith("MCM|"):
                _, file, mk = k.split("|", 2)
                t = mcm_inv.get(file)
                if t is None:
                    stats["menu_no_instalado"] += 1
                    continue
                if file not in mcm_en:
                    try:
                        mcm_en[file] = read_translation_file(Path(t["path_english"]))
                    except OSError:
                        mcm_en[file] = {}
                en = mcm_en[file].get(mk)
                if en is not None and huella(en) == r["h"]:
                    mcm_es[file][mk] = r["es"]
                    stats["menus"] += 1
                else:
                    stats["no_coincide"] += 1
                continue
            if k in hechas:
                continue
            en = actual.get(k)
            if en is None:
                stats["texto_no_instalado"] += 1
            elif huella(en) != r["h"]:
                stats["no_coincide"] += 1        # el mod cambió desde que se tradujo: se queda en inglés
            else:
                add(k, r["es"], "proyecto")

    # 3. Escribir el mod (solo nuestros archivos)
    root = out / DSD_DIR
    for owner, entries in by_owner.items():
        d = root / owner
        d.mkdir(parents=True, exist_ok=True)
        rows = [entries[k] for k in sorted(entries)]
        tmp = d / (OWN_FILE + ".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / OWN_FILE)
    stats["plugins_con_traduccion"] = len(by_owner)
    tdir = out / "Interface" / "translations"
    for file, done in mcm_es.items():
        t = mcm_inv[file]
        name = Path(t["path_english"]).name
        lines = [f"{k}\t{done.get(k, v)}" for k, v in mcm_en[file].items()]
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / (name[: -len("english.txt")] + "SPANISH.txt")).write_text("\r\n".join(lines) + "\r\n",
                                                                          encoding="utf-16")
        stats["archivos_menu"] += 1
    if oficial and oficial.exists():
        for f in oficial.rglob("nolvus-es-oficial.json"):
            dest = out / f.relative_to(oficial)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest)
            stats["archivos_oficiales"] += 1
    return dict(stats)
