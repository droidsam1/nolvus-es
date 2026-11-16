"""Alternativa a Ollama: traducir lo pendiente con la API por lotes de Anthropic o de OpenAI.

Usa la misma base de datos, las mismas instrucciones, glosario y validación que la traducción
con Ollama. Las dos cosas pueden ir a la vez: lo que se envía a la API queda reservado
(estado "lote") y Ollama no lo toca.

Configuración: archivo API.txt junto a los .bat (no se sube al repositorio):
    clave=sk-ant-...        (Anthropic)  o  clave=sk-...  (OpenAI)
    modelo=claude-sonnet-5-5               (opcional en Anthropic; obligatorio en OpenAI)

Uso:
    python -m nolvus_es.lotes auto --data data      enviar, esperar, recoger y repetir hasta acabar
    python -m nolvus_es.lotes estimar --data data   cuánto se enviaría (peticiones y tokens)
    python -m nolvus_es.lotes estado --data data
Se puede cerrar en cualquier momento: los lotes siguen en el servidor y se recogen al volver.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .glossary import Glossary
from .markers import protect
from .translate import (MAX_ATTEMPTS, SYSTEM, _counts, _examples, _split_long, finalize, open_db,
                        parse_reply, user_prompt)

REPO = Path(__file__).resolve().parent.parent
ANTHROPIC_DEFAULT = "claude-sonnet-5-5"
MAX_REQ_PER_BATCH = 4000


# ----------------------------------------------------------------- configuración

def leer_config(path: Path) -> dict:
    cfg = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip().lower()] = v.strip()
    clave = cfg.get("clave", "")
    if not clave:
        sys.exit(f"Falta la clave en {path}. Ábrelo, pega tu clave después de 'clave=' y guarda.")
    prov = "anthropic" if clave.startswith("sk-ant-") else "openai"
    modelo = cfg.get("modelo") or (ANTHROPIC_DEFAULT if prov == "anthropic" else "")
    if not modelo:
        sys.exit(f"Con una clave de OpenAI hay que indicar el modelo en {path} (modelo=...).")
    return {"proveedor": prov, "clave": clave, "modelo": modelo}


def _tablas(db):
    db.execute("""CREATE TABLE IF NOT EXISTS lotes(id TEXT PRIMARY KEY, proveedor TEXT, modelo TEXT,
                  creado REAL, estado TEXT, peticiones INTEGER)""")
    db.execute("""CREATE TABLE IF NOT EXISTS lote_peticiones(custom_id TEXT PRIMARY KEY, lote_id TEXT,
                  uids TEXT, parte INTEGER, partes INTEGER)""")


# ----------------------------------------------------------------- HTTP

def _http(method: str, url: str, headers: dict, body: bytes | None = None, timeout: int = 300) -> bytes:
    for intento in range(5):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:500]
            if e.code in (429, 500, 502, 503, 529) and intento < 4:
                time.sleep(10 * (intento + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}") from None
        except urllib.error.URLError:
            if intento < 4:
                time.sleep(10 * (intento + 1))
                continue
            raise
    raise RuntimeError("sin respuesta")


class Anthropic:
    URL = os.environ.get("NOLVUS_ES_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages/batches")

    def __init__(self, clave):
        self.h = {"x-api-key": clave, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def crear(self, modelo, peticiones):
        reqs = [{"custom_id": cid, "params": {"model": modelo, "max_tokens": mt, "system": SYSTEM,
                                              "messages": [{"role": "user", "content": prompt}]}}
                for cid, prompt, mt in peticiones]
        r = json.loads(_http("POST", self.URL, self.h, json.dumps({"requests": reqs}).encode()))
        return r["id"]

    def estado(self, lote_id):
        r = json.loads(_http("GET", f"{self.URL}/{lote_id}", self.h))
        return ("terminado" if r["processing_status"] == "ended" else "en curso"), r

    def resultados(self, info):
        raw = _http("GET", info["results_url"], self.h, timeout=900).decode("utf-8")
        for line in raw.splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            res = r.get("result", {})
            if res.get("type") == "succeeded":
                text = "".join(c.get("text", "") for c in res["message"]["content"] if c.get("type") == "text")
                yield r["custom_id"], text, None
            else:
                yield r["custom_id"], None, res.get("type", "error")


class OpenAI:
    BASE = "https://api.openai.com/v1"

    def __init__(self, clave):
        self.auth = {"Authorization": f"Bearer {clave}"}

    def crear(self, modelo, peticiones):
        jsonl = "".join(json.dumps({"custom_id": cid, "method": "POST", "url": "/v1/chat/completions",
                                    "body": {"model": modelo, "response_format": {"type": "json_object"},
                                             "messages": [{"role": "system", "content": SYSTEM},
                                                          {"role": "user", "content": prompt}]}},
                                   ensure_ascii=False) + "\n" for cid, prompt, _ in peticiones).encode("utf-8")
        b = uuid.uuid4().hex
        body = (f"--{b}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
                f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"lote.jsonl\"\r\n"
                f"Content-Type: application/jsonl\r\n\r\n").encode() + jsonl + f"\r\n--{b}--\r\n".encode()
        f = json.loads(_http("POST", f"{self.BASE}/files",
                             {**self.auth, "Content-Type": f"multipart/form-data; boundary={b}"}, body))
        r = json.loads(_http("POST", f"{self.BASE}/batches", {**self.auth, "Content-Type": "application/json"},
                             json.dumps({"input_file_id": f["id"], "endpoint": "/v1/chat/completions",
                                         "completion_window": "24h"}).encode()))
        return r["id"]

    def estado(self, lote_id):
        r = json.loads(_http("GET", f"{self.BASE}/batches/{lote_id}", self.auth))
        fin = r["status"] in ("completed", "failed", "expired", "cancelled")
        return ("terminado" if fin else "en curso"), r

    def resultados(self, info):
        for key in ("output_file_id", "error_file_id"):
            if not info.get(key):
                continue
            raw = _http("GET", f"{self.BASE}/files/{info[key]}/content", self.auth, timeout=900).decode("utf-8")
            for line in raw.splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                resp = r.get("response") or {}
                if resp.get("status_code") == 200:
                    yield r["custom_id"], resp["body"]["choices"][0]["message"]["content"], None
                else:
                    yield r["custom_id"], None, str(r.get("error") or resp.get("status_code"))


def cliente(cfg):
    return Anthropic(cfg["clave"]) if cfg["proveedor"] == "anthropic" else OpenAI(cfg["clave"])


# ----------------------------------------------------------------- preparar peticiones

def _items(db, uids: list[str], gl: Glossary | None) -> list[dict]:
    out = []
    for uid in uids:
        en, kind, ref_es, mod, words = db.execute(
            "SELECT en, kind, ref_es, mod, words FROM units WHERE uid=?", (uid,)).fetchone()
        masked, tokens = protect(en)
        out.append({"uid": uid, "en": en, "kind": kind, "ref_es": ref_es, "mod": mod, "words": words,
                    "masked": masked, "tokens": tokens, "terms": gl.find(en) if gl else []})
    return out


def planificar(db, gl: Glossary, cfg_prompt: dict, max_palabras: int | None,
               lote_words: int = 400, lote_items: int = 25) -> list[tuple[str, list[str], int, int, str, int]]:
    """-> [(custom_id, uids, parte, partes, prompt, max_tokens)] con todo lo pendiente."""
    rows = db.execute("SELECT uid FROM units WHERE status='pending' ORDER BY prio, plugin, kind, uid").fetchall()
    seq = uuid.uuid4().hex[:6]
    plan, grupo, gw, total, n = [], [], 0, 0, 0

    def cerrar():
        nonlocal grupo, gw, n
        if grupo:
            n += 1
            w = sum(it["words"] for it in grupo)
            plan.append((f"{seq}-{n}", [it["uid"] for it in grupo], 0, 1,
                         user_prompt(grupo, cfg_prompt), min(8192, 400 + w * 4)))
        grupo, gw = [], 0

    for (uid,) in rows:
        it = _items(db, [uid], gl)[0]
        if max_palabras and total + it["words"] > max_palabras:
            break
        total += it["words"]
        if it["words"] > 500:                       # libros: por trozos, cada uno su petición
            trozos = _split_long(it["masked"])
            n += 1
            for k, chunk in enumerate(trozos):
                sub = dict(it, masked=chunk)
                plan.append((f"{seq}-{n}-p{k}", [uid], k, len(trozos), user_prompt([sub], cfg_prompt),
                             min(8192, 400 + len(chunk.split()) * 4)))
            continue
        if grupo and (grupo[0]["kind"] != it["kind"] or grupo[0]["mod"] != it["mod"]
                      or len(grupo) >= lote_items or gw + it["words"] > lote_words):
            cerrar()
        grupo.append(it)
        gw += it["words"]
    cerrar()
    return plan


# ----------------------------------------------------------------- órdenes

def enviar(data: Path, cfg: dict, max_palabras: int | None, si: bool) -> int:
    db = open_db(data)
    _tablas(db)
    gl = Glossary.load(data)
    plan = planificar(db, gl, {"examples": _examples(data)}, max_palabras)
    if not plan:
        return 0
    uids = {u for p in plan for u in p[1]}
    chars = sum(len(SYSTEM) + len(p[4]) for p in plan)
    out_tok = sum(p[5] for p in plan) // 3
    print(f"Se enviarán {len(uids):,} textos en {len(plan):,} peticiones a {cfg['proveedor']} ({cfg['modelo']}).")
    print(f"Aproximadamente {chars // 3:,} tokens de entrada y {out_tok:,} de salida (los precios por lotes "
          "suelen ser la mitad de los normales; consulta la página de precios de tu proveedor).")
    if not si and input("¿Enviar? [s/N] ").strip().lower() not in ("s", "si", "sí"):
        return 0
    api = cliente(cfg)
    enviados = 0
    trozos, cur = [], []
    for p in plan:                     # los trozos de un mismo libro van siempre en el mismo lote
        if len(cur) >= MAX_REQ_PER_BATCH and p[2] == 0:
            trozos.append(cur)
            cur = []
        cur.append(p)
    if cur:
        trozos.append(cur)
    for trozo in trozos:
        lote_id = api.crear(cfg["modelo"], [(cid, prompt, mt) for cid, _, _, _, prompt, mt in trozo])
        with db:
            db.execute("INSERT INTO lotes VALUES(?,?,?,?,?,?)",
                       (lote_id, cfg["proveedor"], cfg["modelo"], time.time(), "en curso", len(trozo)))
            for cid, us, parte, partes, _, _ in trozo:
                db.execute("INSERT INTO lote_peticiones VALUES(?,?,?,?,?)",
                           (cid, lote_id, json.dumps(us), parte, partes))
                db.executemany("UPDATE units SET status='lote' WHERE uid=? AND status='pending'", [(u,) for u in us])
        enviados += len(trozo)
        print(f"  lote {lote_id}: {len(trozo)} peticiones", flush=True)
    return enviados


def recoger(data: Path, cfg: dict) -> tuple[int, int]:
    """Recoge los lotes terminados. -> (lotes que siguen en curso, textos guardados)"""
    db = open_db(data)
    _tablas(db)
    api = cliente(cfg)
    abiertos = db.execute("SELECT id, modelo FROM lotes WHERE estado='en curso' AND proveedor=?",
                          (cfg["proveedor"],)).fetchall()
    siguen, guardados = 0, 0
    for lote_id, modelo in abiertos:
        est, info = api.estado(lote_id)
        if est != "terminado":
            siguen += 1
            continue
        textos: dict[str, dict[int, str]] = {}     # uid -> {parte: texto con fichas}
        partes_de: dict[str, int] = {}
        errores: dict[str, str] = {}
        for cid, text, err in api.resultados(info):
            row = db.execute("SELECT uids, parte, partes FROM lote_peticiones WHERE custom_id=?", (cid,)).fetchone()
            if not row:
                continue
            uids, parte, partes = json.loads(row[0]), row[1], row[2]
            if err or not text:
                for u in uids:
                    errores[u] = f"api: {err}"
                continue
            items = _items(db, uids, None)
            try:
                got = parse_reply(text, items)
            except (ValueError, KeyError):
                for u in uids:
                    errores[u] = "api: respuesta no es JSON"
                continue
            for u in uids:
                if u in got:
                    textos.setdefault(u, {})[parte] = got[u]
                    partes_de[u] = partes
        # Todos los uid de este lote, incluidos los que no aparecen en los resultados
        todos = {u for (us,) in db.execute("SELECT uids FROM lote_peticiones WHERE lote_id=?", (lote_id,))
                 for u in json.loads(us)}
        now = time.time()
        with db:
            for u in todos:
                if db.execute("SELECT status FROM units WHERE uid=?", (u,)).fetchone()[0] != "lote":
                    continue                              # Ollama ya lo hizo, o ya se recogió
                partes = partes_de.get(u)
                got = textos.get(u, {})
                es, err = None, errores.get(u, "sin respuesta para este texto")
                if partes and len(got) == partes:
                    es, err = finalize(_items(db, [u], None)[0], "".join(got[k] for k in range(partes)))
                elif partes:
                    err = "api: faltan trozos del texto"
                if es is not None:
                    db.execute("UPDATE units SET status='done', es=?, source='ia', model=?, err=NULL, updated=? "
                               "WHERE uid=?", (es, f"api:{modelo}", now, u))
                    guardados += 1
                else:
                    db.execute("UPDATE units SET attempts=attempts+1, err=?, updated=?, "
                               "status=CASE WHEN attempts+1>=? THEN 'failed' ELSE 'pending' END WHERE uid=?",
                               (err[:300], now, MAX_ATTEMPTS, u))
            db.execute("UPDATE lotes SET estado='recogido' WHERE id=?", (lote_id,))
        print(f"  lote {lote_id} recogido", flush=True)
    return siguen, guardados


def estado(data: Path):
    db = open_db(data)
    _tablas(db)
    for st, v in _counts(db).items():
        print(f"  {st:<10} {v['textos']:>8,} textos  {v['palabras']:>10,} palabras")
    for row in db.execute("SELECT id, proveedor, modelo, estado, peticiones FROM lotes ORDER BY creado"):
        print("  lote", *row)


def auto(data: Path, cfg: dict, max_palabras: int | None, si: bool, reintentar: bool, espera: int):
    db = open_db(data)
    _tablas(db)
    if reintentar:
        with db:
            n = db.execute("UPDATE units SET status='pending', attempts=0 WHERE status='failed'").rowcount
        if n:
            print(f"{n} textos fallidos vuelven a la cola.")
    preguntado, enviado = si, False
    while True:
        siguen, guardados = recoger(data, cfg)
        if guardados:
            print(f"{time.strftime('%H:%M:%S')}  +{guardados:,} textos guardados", flush=True)
        if siguen:
            print(f"\r{time.strftime('%H:%M:%S')}  {siguen} lote(s) en curso en el servidor; "
                  f"compruebo cada {espera // 60} min (puedes cerrar y volver luego)…", end="", flush=True)
            time.sleep(espera)
            continue
        if enviado or not enviar(data, cfg, max_palabras, preguntado):
            break
        preguntado = True
        enviado = bool(max_palabras)      # con --max-palabras: un solo envío (para probar)
    print()
    estado(data)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("orden", choices=["auto", "estimar", "estado", "recoger"])
    ap.add_argument("--data", default="data")
    ap.add_argument("--config", default=str(REPO / "API.txt"))
    ap.add_argument("--max-palabras", type=int, help="enviar como mucho estas palabras (para probar)")
    ap.add_argument("--reintentar-fallidos", action="store_true")
    ap.add_argument("--espera", type=int, default=300, help="segundos entre comprobaciones")
    ap.add_argument("--si", action="store_true", help="no pedir confirmación")
    a = ap.parse_args(argv)
    data = Path(a.data)
    if a.orden == "estado":
        return estado(data)
    if a.orden == "estimar":
        db = open_db(data)
        plan = planificar(db, Glossary.load(data), {"examples": _examples(data)}, a.max_palabras)
        chars = sum(len(SYSTEM) + len(p[4]) for p in plan)
        print(f"{len({u for p in plan for u in p[1]}):,} textos · {len(plan):,} peticiones · "
              f"~{chars // 3:,} tokens de entrada · ~{sum(p[5] for p in plan) // 3:,} de salida")
        return
    cfg = leer_config(Path(a.config))
    if a.orden == "recoger":
        print(recoger(data, cfg))
        return
    auto(data, cfg, a.max_palabras, a.si, a.reintentar_fallidos, a.espera)


if __name__ == "__main__":
    main()
