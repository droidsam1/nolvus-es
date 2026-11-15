"""Fase 4: traducción con IA local (Ollama), reanudable y segura ante cortes.

Todo el estado vive en data/trabajo.sqlite:
  * units: cada texto inglés ÚNICO (por tipo de campo) con su estado
           pending -> done | failed   (failed = 3 intentos rechazados por el validador)
  * keys:  cada campo concreto del juego (clave DSD o línea de menú) -> unidad
Cada lote terminado se guarda en una transacción: si se apaga el PC a mitad, como mucho
se repite el lote que estaba en curso. Volver a lanzar `run` continúa donde se quedó.

Comandos:
  prepare  Crea/actualiza la lista de trabajo (idempotente; respeta lo ya traducido)
  run      Traduce lo pendiente con Ollama (se puede parar en cualquier momento)
  status   Muestra el progreso y una estimación del tiempo restante
"""
from __future__ import annotations

import argparse
import os
import concurrent.futures as cf
import gzip
import hashlib
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .glossary import Glossary
from .lang import classify
from .markers import protect, restore, validate

DB_NAME = "trabajo.sqlite"
MAX_ATTEMPTS = 3

# ---------------------------------------------------------------- tipos de texto

KIND_ORDER = {"MCM": 0, "FULL": 1, "SHRT": 1, "TNAM": 1, "ITXT": 1, "RNAM": 1, "EPF2": 1,
              "MNAM": 1, "FNAM": 1, "DESC": 2, "DNAM": 2, "NNAM": 2, "CNAM": 2, "NAM1": 3,
              "BOOK DESC": 4}

KIND_GUIDE = {
    "MCM": "Opción o ayuda de un menú de configuración (MCM). Claro y conciso, estilo de interfaz.",
    "FULL": "Nombre que ve el jugador (objeto, lugar, personaje, hechizo, misión...). Corto, en "
            "minúscula salvo la primera letra y los nombres propios, como en el Skyrim oficial "
            "('Espada de hierro', 'Grimorio: conjurar lord dremora').",
    "DESC": "Descripción de juego (efecto, ventaja, objeto, pantalla de carga). Clara y fiel; "
            "respeta los números y marcadores.",
    "DNAM": "Descripción de un efecto mágico. Estilo de las descripciones oficiales de Skyrim.",
    "NNAM": "Objetivo de misión: breve e imperativo, como en el diario del juego.",
    "CNAM": "Entrada del diario de misión, en primera persona del jugador y en pasado/presente "
            "como el original.",
    "NAM1": "Línea de diálogo hablada por un personaje. Natural, oral, con su personalidad, "
            "su registro (culto, vulgar, arcaico...) y su humor. Nada de traducción literal.",
    "RNAM": "Texto corto de acción o respuesta del jugador en un diálogo.",
    "BOOK DESC": "Texto de un libro, carta o nota del mundo de Skyrim. Literario y con la voz del "
                 "autor (antiguo, erudito, coloquial...). Conserva párrafos y formato.",
    "ITXT": "Botón de un mensaje: muy corto.",
}

SYSTEM = """Eres un traductor profesional de videojuegos que traduce Skyrim y sus mods del inglés al español de España.
Reglas:
1. Español de España (tú/vosotros), con la terminología oficial de la versión española de Skyrim.
2. Mantén el sentido, el tono y la intención del original; no resumas ni añadas nada.
3. Usa EXACTAMENTE los términos del glosario que se te dan. Los nombres propios que no estén en el glosario se dejan como están.
4. Las fichas como ⟦1⟧, ⟦2⟧ son marcadores del juego: cópialas tal cual, una vez cada una, en el lugar que corresponda. Nunca las traduzcas ni las cambies.
5. Respeta los saltos de línea del original.
6. Si un texto es un identificador interno (sin sentido para el jugador), devuélvelo sin cambios.
7. Mayúsculas a la española: solo la primera palabra y los nombres propios ("Tamaño mínimo del widget", nunca "Tamaño Mínimo del Widget"), aunque el inglés ponga mayúscula en cada palabra.
8. Responde solo con el JSON pedido."""

SCHEMA = {"type": "object", "properties": {"t": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "string"}, "es": {"type": "string"}},
    "required": ["id", "es"]}}}, "required": ["t"]}


def kind_family(kind: str) -> str:
    if kind == "MCM":
        return "MCM"
    if kind == "BOOK DESC":
        return "BOOK DESC"
    return kind.split(" ")[-1]


# ---------------------------------------------------------------- base de datos

def open_db(data: Path) -> sqlite3.Connection:
    db = sqlite3.connect(data / DB_NAME, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS units(
        uid TEXT PRIMARY KEY, en TEXT NOT NULL, kind TEXT NOT NULL, ref_es TEXT, ref_en TEXT,
        plugin TEXT, mod TEXT, edid TEXT, prio INTEGER, words INTEGER,
        status TEXT NOT NULL DEFAULT 'pending', es TEXT, source TEXT, model TEXT,
        attempts INTEGER NOT NULL DEFAULT 0, err TEXT, updated REAL);
    CREATE INDEX IF NOT EXISTS units_todo ON units(status, prio);
    CREATE TABLE IF NOT EXISTS keys(key TEXT PRIMARY KEY, uid TEXT NOT NULL, plugin TEXT, en TEXT);
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    """)
    return db


def uid_for(en: str, kind: str, ref_es: str | None) -> str:
    h = hashlib.sha1(f"{kind}\x1f{en}\x1f{ref_es or ''}".encode("utf-8")).hexdigest()
    return h[:20]


# ---------------------------------------------------------------- prepare

def prepare(data: Path) -> dict:
    from .inventory import OFFICIAL
    from .mcm import read_translation_file

    state = json.loads((data / "plugins.json").read_text(encoding="utf-8"))
    rank = {}
    mw = data / "mods_by_words.json"
    if mw.exists():
        for i, r in enumerate(json.loads(mw.read_text(encoding="utf-8"))):
            rank[r["mod"]] = i
    gl = json.loads((data / "glossary.official.json").read_text(encoding="utf-8"))
    gl_exact = {r["en"]: r for r in gl if r["confidence"] >= 0.8}

    # 1. Quién gana cada campo de registros NO oficiales
    winner = {}
    for p in state["plugins"]:
        s = p.get("summary") or {}
        if s.get("official") or s.get("error"):
            continue
        f = data / "extract" / f'{p["name"]}.jsonl.gz'
        if not f.exists():
            continue
        masters = s.get("masters", [])
        for line in gzip.open(f, "rt", encoding="utf-8"):
            r = json.loads(line)
            i = r["fid"] >> 24
            owner = masters[i] if i < len(masters) else p["name"]
            if OFFICIAL.match(owner):
                continue
            local = r["fid"] & 0xFFFFFF
            di = r.get("di")
            dkey = "" if di is None else (f"{di[0]}:{di[1]}" if isinstance(di, list) else str(di))
            winner[f'{owner}|{local:06X}|{r["t"]} {r["f"]}|{dkey}'] = (p["name"], p["mod"], r)

    segs = []
    for key, (plugin, mod, r) in winner.items():
        if r["s"] is None or r["lang"] not in ("en", "short"):
            continue
        segs.append((key, r["s"], f'{r["t"]} {r["f"]}', None, None, plugin, mod, r.get("edid")))
    # 2. Textos del juego base que los mods cambiaron (fase 2), con el español oficial de referencia
    q = data / "queue_vanilla_changed.jsonl.gz"
    if q.exists():
        for line in gzip.open(q, "rt", encoding="utf-8"):
            r = json.loads(line)
            segs.append((r["key"], r["en"], r["key"].split("|")[2], r.get("ref_es"), r.get("ref_en"),
                         r["plugin"], None, r.get("edid")))
    # 3. Menús MCM sin español real
    mcm_meta = {}
    mi = data / "mcm_inventory.json"
    if mi.exists():
        for t in json.loads(mi.read_text(encoding="utf-8"))["translations"]:
            if t.get("spanish_is_real"):
                continue
            try:
                entries = read_translation_file(Path(t["path_english"]))
            except OSError:
                continue
            name = Path(t["path_english"]).name
            mcm_meta[t["file"]] = {"filename": name[: -len("english.txt")] + "SPANISH.txt",
                                   "entries": list(entries.items())}
            for k, v in entries.items():
                # Fuera: tablas internas con tabuladores (p. ej. B.O.O.B.I.E.S) e identificadores
                if "\t" in v or re.fullmatch(r"[\w.\-]+", v.strip()) and ("_" in v or re.search(r"[a-z][A-Z]", v)):
                    continue
                if re.search(r"[A-Za-z]", v):
                    segs.append((f'MCM|{t["file"]}|{k}', v, "MCM", None, None, t["file"], t["mod"], None))
    # 4. Traducciones importadas válidas (fase 3): esas claves no necesitan IA
    imported = {}
    for f in (data / "tm").glob("*.import.jsonl.gz") if (data / "tm").exists() else []:
        for line in gzip.open(f, "rt", encoding="utf-8"):
            r = json.loads(line)
            if r["status"] == "ok":
                imported[r["key"]] = r["en"]

    unit_rows, key_rows, glos = {}, [], {}
    stats = {"campos": 0, "importados": 0}
    now = time.time()
    for key, en, kind, ref_es, ref_en, plugin, mod, edid in segs:
        if imported.get(key) == en:
            stats["importados"] += 1
            continue
        uid = uid_for(en, kind, ref_es)
        if uid not in unit_rows:
            fam = kind_family(kind)
            prio = (-10 if kind == "MCM"            # menús primero: pocos y muy visibles
                    else rank.get(mod, 5000) * 10 + KIND_ORDER.get(kind, KIND_ORDER.get(fam, 3)))
            unit_rows[uid] = (uid, en, kind, ref_es, ref_en, plugin, mod, edid, prio, len(en.split()), now)
            # Nombres que coinciden exactamente con el glosario oficial: no hace falta IA
            g = gl_exact.get(en.strip())
            if g and fam in ("FULL", "SHRT") and not ref_es:
                glos[uid] = g["es"]
        key_rows.append((key, uid, plugin, en))
    stats["campos"] = len(key_rows)
    db = open_db(data)
    with db:  # todo en una transacción: si se corta, no queda a medias
        db.executemany("""INSERT INTO units(uid,en,kind,ref_es,ref_en,plugin,mod,edid,prio,words,updated)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(uid) DO UPDATE SET prio=excluded.prio, plugin=excluded.plugin,
                                                         mod=excluded.mod""", unit_rows.values())
        db.executemany("UPDATE units SET status='done', es=?, source='glosario', updated=? "
                       "WHERE uid=? AND status!='done'", [(es, now, uid) for uid, es in glos.items()])
        db.execute("DELETE FROM keys")
        db.executemany("INSERT OR REPLACE INTO keys(key,uid,plugin,en) VALUES(?,?,?,?)", key_rows)
        light = {p["name"]: bool((p.get("summary") or {}).get("is_light")) for p in state["plugins"]}
        db.execute("INSERT OR REPLACE INTO meta VALUES('light_plugins', ?)", (json.dumps(light),))
        db.execute("INSERT OR REPLACE INTO meta VALUES('mcm_files', ?)", (json.dumps(mcm_meta, ensure_ascii=False),))
    stats["resueltos_por_glosario"] = len(glos)
    stats.update(_counts(db))
    return stats


# ---------------------------------------------------------------- run

def _examples(data: Path) -> dict[str, list]:
    """2-3 ejemplos oficiales por tipo de texto, para fijar estilo y mayúsculas."""
    off = json.load(gzip.open(data / "official.json.gz", "rt", encoding="utf-8"))
    by = {}
    for key, (en, es, _) in sorted(off.items(), key=lambda kv: hashlib.md5(kv[0].encode()).hexdigest()):
        if not en or not es or "<" in en:
            continue
        ftype = key.split("|")[2]
        fam = "BOOK DESC" if ftype == "BOOK DESC" else ftype.split(" ")[-1]
        lim = {"FULL": (2, 6), "NAM1": (6, 25), "BOOK DESC": (20, 60)}.get(fam, (4, 30))
        if not lim[0] <= len(en.split()) <= lim[1]:
            continue
        lst = by.setdefault(fam, [])
        if len(lst) < 3:
            lst.append((en, es))
    return by


_NO_THINK = {"supported": True}


def _ollama(url: str, model: str, messages: list, ctx: int, timeout: int = 900) -> str:
    payload = {"model": model, "stream": False, "format": SCHEMA, "keep_alive": "30m",
               "options": {"temperature": 0.2, "num_ctx": ctx}, "messages": messages}
    if _NO_THINK["supported"]:
        payload["think"] = False      # sin "razonamiento": más rápido y sin respuestas vacías
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            msg = json.loads(r.read().decode("utf-8"))["message"]
    except urllib.error.HTTPError as e:
        if _NO_THINK["supported"] and "think" in e.read().decode("utf-8", "replace").lower():
            _NO_THINK["supported"] = False           # modelo sin modo de razonamiento: reintentar sin él
            return _ollama(url, model, messages, ctx, timeout)
        raise
    content = (msg.get("content") or "").strip()
    if not content:
        raise ValueError("respuesta vacía de Ollama")
    return content


def _gpu_report(url: str) -> str:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/ps", timeout=10) as r:
            ms = json.loads(r.read().decode("utf-8")).get("models", [])
    except Exception as e:  # noqa: BLE001
        return f"(no se pudo consultar Ollama: {e})"
    out = []
    for m in ms:
        size, vram = m.get("size", 0), m.get("size_vram", 0)
        pct = 100 * vram / size if size else 0
        out.append(f'{m.get("name")}: {size / 2**30:.1f} GB, {pct:.0f} % en la GPU'
                   + ("" if pct >= 99 else "  <-- parte en RAM: irá lento"))
    return "; ".join(out) or "(ningún modelo cargado todavía)"


def _split_long(text: str, max_words: int = 450) -> list[str]:
    """Trocea textos largos (libros) por párrafos, sin romper fichas ni etiquetas."""
    parts = re.split(r"(\n\s*\n|⟦\d+⟧)", text)
    chunks, cur, words = [], "", 0
    for p in parts:
        w = len(p.split())
        if cur and words + w > max_words and not re.fullmatch(r"⟦\d+⟧", p):
            chunks.append(cur)
            cur, words = "", 0
        cur += p
        words += w
    if cur:
        chunks.append(cur)
    return chunks


def _translate_batch(items: list[dict], cfg: dict) -> dict[str, str]:
    """items: [{uid, masked, kind, mod, ref_es, terms}] -> {uid: texto traducido (aún con fichas)}"""
    kind = items[0]["kind"]
    fam = kind_family(kind)
    lines = [f"Tipo de texto: {KIND_GUIDE.get(fam, KIND_GUIDE['DESC'])}"]
    if items[0].get("mod"):
        lines.append(f"Mod de origen: {items[0]['mod']}")
    terms = {}
    for it in items:
        for t in it["terms"]:
            terms[t["en"]] = t
    keep = [t["en"] for t in terms.values() if t.get("keep")]
    tr = [f'{t["en"]} → {t["es"]}' for t in terms.values() if not t.get("keep")]
    if tr:
        lines.append("Glosario obligatorio:\n" + "\n".join(tr[:40]))
    if keep:
        lines.append("No se traducen: " + ", ".join(keep[:30]))
    ex = cfg["examples"].get(fam) or []
    if ex:
        lines.append("Ejemplos de la traducción oficial de este tipo de texto:\n" +
                     "\n".join(f"EN: {a}\nES: {b}" for a, b in ex))
    payload = []
    for i, it in enumerate(items, 1):
        d = {"id": str(i), "en": it["masked"]}
        if it.get("ref_es"):
            d["referencia_oficial"] = it["ref_es"]
        payload.append(d)
    if any(it.get("ref_es") for it in items):
        lines.append("Si hay 'referencia_oficial', es la traducción oficial de una versión anterior del texto: "
                     "úsala como base y cambia solo lo que haya cambiado en el inglés.")
    lines.append('Traduce cada "en" y responde con {"t":[{"id":"1","es":"..."}, ...]} en el mismo orden.\n'
                 + json.dumps(payload, ensure_ascii=False))
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n\n".join(lines)}]
    words = sum(len(it["masked"].split()) for it in items)
    ctx = 4096 if words < 250 else 8192
    raw = _ollama(cfg["url"], cfg["model"], msgs, ctx)
    out = {}
    for r in json.loads(raw).get("t", []):
        idx = int(str(r.get("id", "0")).strip() or 0) - 1
        if 0 <= idx < len(items):
            out[items[idx]["uid"]] = r.get("es", "")
    return out


def _work(batch: list[dict], cfg: dict) -> dict[str, tuple[str | None, str | None]]:
    """Devuelve {uid: (traducción final o None, error o None)}."""
    res = {}
    try:
        if len(batch) == 1 and batch[0]["words"] > 500:     # libro o texto largo: por trozos
            it = batch[0]
            parts = []
            for chunk in _split_long(it["masked"]):
                sub = dict(it, masked=chunk)
                parts.append(_translate_batch([sub], cfg).get(it["uid"], ""))
            got = {it["uid"]: "".join(parts)}
        else:
            got = _translate_batch(batch, cfg)
    except Exception as e:  # red, Ollama caído, JSON inválido...: se reintenta más tarde
        return {it["uid"]: (None, f"lote: {type(e).__name__}: {str(e)[:150]}") for it in batch}
    for it in batch:
        es = got.get(it["uid"])
        if not es:
            res[it["uid"]] = (None, "sin respuesta para este texto")
            continue
        final = restore(es, it["tokens"])
        # Conservar espacios iniciales/finales del original
        lead = it["en"][:len(it["en"]) - len(it["en"].lstrip())]
        trail = it["en"][len(it["en"].rstrip()):]
        final = lead + final.strip() + trail
        errs = validate(it["en"], final)
        if not errs and it["words"] >= 6 and classify(final) == "en":
            errs = ["parece seguir en inglés"]
        res[it["uid"]] = (final, None) if not errs else (None, "; ".join(errs)[:300])
    return res


def _next_batches(db, gl: Glossary, limit_words: int, limit_items: int, n: int,
                  busy: set) -> list[list[dict]]:
    rows = db.execute("""SELECT uid,en,kind,ref_es,mod,words,attempts FROM units
                         WHERE status='pending' ORDER BY prio, plugin, kind, uid LIMIT ?""",
                      (max(n * limit_items, 50) + len(busy),)).fetchall()
    batches, cur, cur_w = [], [], 0
    for uid, en, kind, ref_es, mod, words, attempts in rows:
        if uid in busy:
            continue
        masked, tokens = protect(en)
        it = {"uid": uid, "en": en, "kind": kind, "ref_es": ref_es, "mod": mod, "words": words,
              "masked": masked, "tokens": tokens, "terms": gl.find(en)}
        alone = attempts > 0 or words > 300
        if alone:
            batches.append([it])
            continue
        if cur and (cur[0]["kind"] != kind or cur[0]["mod"] != mod or len(cur) >= limit_items
                    or cur_w + words > limit_words):
            batches.append(cur)
            cur, cur_w = [], 0
        cur.append(it)
        cur_w += words
        if len(batches) >= n:
            break
    if cur and len(batches) < n:
        batches.append(cur)
    return batches[:n]


def run(data: Path, model: str, url: str, workers: int, hours: float | None,
        batch_words: int, batch_items: int) -> None:
    db = open_db(data)
    gl = Glossary.load(data)
    cfg = {"model": model, "url": url, "examples": _examples(data)}
    stop_file = data / "PARAR"
    if stop_file.exists():
        stop_file.unlink()
    t_end = time.time() + hours * 3600 if hours else None
    print(f"Modelo: {model} · {workers} en paralelo · Ollama en {url}")
    print("Puedes cerrar esta ventana o apagar el PC cuando quieras: el progreso se guarda lote a lote.")
    _print_status(db)
    done_words, t0 = 0, time.time()
    in_flight: dict = {}
    last_report, gpu_checked = 0.0, False
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            while True:
                stopping = stop_file.exists() or (t_end and time.time() > t_end)
                if not stopping:
                    busy = {u for b in in_flight.values() for u in b}
                    want = workers * 2 - len(in_flight)
                    if want > 0:
                        for b in _next_batches(db, gl, batch_words, batch_items, want, busy):
                            fut = pool.submit(_work, b, cfg)
                            in_flight[fut] = [it["uid"] for it in b]
                            busy.update(it["uid"] for it in b)
                            if len(in_flight) >= workers * 2:
                                break
                if not in_flight:
                    break
                finished, _ = cf.wait(list(in_flight), timeout=5, return_when=cf.FIRST_COMPLETED)
                for fut in finished:
                    in_flight.pop(fut)
                    res = fut.result()
                    now = time.time()
                    with db:  # una transacción por lote
                        for uid, (es, err) in res.items():
                            if es is not None:
                                db.execute("UPDATE units SET status='done', es=?, source='ia', model=?, err=NULL, "
                                           "updated=? WHERE uid=?", (es, model, now, uid))
                                done_words += db.execute("SELECT words FROM units WHERE uid=?", (uid,)).fetchone()[0]
                            else:
                                db.execute("UPDATE units SET attempts=attempts+1, err=?, updated=?, "
                                           "status=CASE WHEN attempts+1>=? THEN 'failed' ELSE 'pending' END "
                                           "WHERE uid=?", (err, now, MAX_ATTEMPTS, uid))
                    if not gpu_checked:
                        gpu_checked = True
                        print("\nGPU: " + _gpu_report(url))
                    if time.time() - last_report > 60:
                        last_report = time.time()
                        _write_progress(db, data, model, done_words, time.time() - t0, _gpu_report(url))
                    el = max(time.time() - t0, 1)
                    print(f"\r{time.strftime('%H:%M:%S')}  +{done_words:,} palabras esta sesión "
                          f"({done_words / el * 3600:,.0f}/h)      ", end="", flush=True)
        except KeyboardInterrupt:
            print("\nParando... (lo terminado ya está guardado)")
            os._exit(0)  # salir ya: lo terminado está guardado; lo que estaba en curso se repetirá
    print()
    _print_status(db)


def _write_progress(db, data: Path, model: str, words: int, secs: float, gpu: str) -> None:
    """Resumen legible sin abrir la base de datos (para seguir el progreso desde fuera)."""
    last = db.execute("SELECT kind, en, es FROM units WHERE source='ia' ORDER BY updated DESC LIMIT 30").fetchall()
    errs = db.execute("SELECT err, COUNT(*) FROM units WHERE attempts>0 AND status!='done' "
                      "GROUP BY err ORDER BY 2 DESC LIMIT 10").fetchall()
    info = {"hora": time.strftime("%Y-%m-%d %H:%M:%S"), "modelo": model, "gpu": gpu,
            "sesion_palabras": words, "sesion_palabras_hora": round(words / max(secs, 1) * 3600),
            "estado": _counts(db), "errores": errs,
            "ultimas": [{"tipo": k, "en": e, "es": s} for k, e, s in last]}
    tmp = data / "progreso.json.tmp"
    tmp.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(data / "progreso.json")


# ---------------------------------------------------------------- status

def _counts(db) -> dict:
    out = {}
    for st, n, w in db.execute("SELECT status, COUNT(*), COALESCE(SUM(words),0) FROM units GROUP BY status"):
        out[st] = {"textos": n, "palabras": w}
    return out


def _print_status(db) -> None:
    c = _counts(db)
    tot_w = sum(v["palabras"] for v in c.values()) or 1
    done_w = c.get("done", {}).get("palabras", 0)
    print(f"Progreso: {done_w:,} / {tot_w:,} palabras ({100 * done_w / tot_w:.1f} %) · "
          + " · ".join(f"{k}: {v['textos']:,}" for k, v in sorted(c.items())))
    hour_ago = time.time() - 3600
    rate = db.execute("SELECT COALESCE(SUM(words),0) FROM units WHERE source='ia' AND updated>?",
                      (hour_ago,)).fetchone()[0]
    if rate:
        left = c.get("pending", {}).get("palabras", 0)
        print(f"Ritmo última hora: {rate:,} palabras/h · faltan ~{left / rate:.1f} h de traducción")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--data", default="data")
    r = sub.add_parser("run")
    r.add_argument("--data", default="data")
    r.add_argument("--model", default="gemma4:26b-a4b-it-qat")
    r.add_argument("--url", default="http://localhost:11434")
    r.add_argument("--workers", type=int, default=2)
    r.add_argument("--hours", type=float, default=None, help="parar solo tras N horas")
    r.add_argument("--batch-words", type=int, default=350)
    r.add_argument("--batch-items", type=int, default=20)
    s = sub.add_parser("status"); s.add_argument("--data", default="data")
    a = ap.parse_args(argv)
    data = Path(a.data)
    if a.cmd == "prepare":
        print(json.dumps(prepare(data), ensure_ascii=False, indent=1))
    elif a.cmd == "run":
        run(data, a.model, a.url, a.workers, a.hours, a.batch_words, a.batch_items)
    else:
        _print_status(open_db(data))


if __name__ == "__main__":
    main()
