"""Glosario oficial inglés -> español sacado de los textos de Bethesda.

Se construye a partir de data/official.json.gz (fase 2): para cada nombre en inglés
de un lugar, personaje, facción, raza, grito, hechizo, objeto... se guarda su traducción
oficial más frecuente y las variantes que existan.

Uso:
    python -m nolvus_es.glossary build --data data
    python -m nolvus_es.glossary find --data data "Travel to Whiterun and speak with Jarl Balgruuf"
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# Tipo de registro -> categoría del glosario
KINDS = {
    "CELL": "lugar", "WRLD": "lugar", "LCTN": "lugar", "REFR": "lugar",
    "NPC_": "personaje", "FACT": "facción", "RACE": "raza", "CLAS": "clase",
    "SHOU": "grito", "WOOP": "palabra de poder", "SPEL": "hechizo", "SCRL": "pergamino",
    "MGEF": "efecto mágico", "ENCH": "encantamiento", "PERK": "ventaja", "AVIF": "habilidad",
    "QUST": "misión", "BOOK": "libro", "WEAP": "arma", "ARMO": "armadura", "AMMO": "munición",
    "INGR": "ingrediente", "ALCH": "poción/comida", "MISC": "objeto", "KEYM": "llave",
    "SLGM": "gema de alma", "ACTI": "objeto", "CONT": "contenedor", "FURN": "mueble",
    "LIGH": "objeto", "APPA": "utensilio", "DOOR": "puerta", "FLOR": "planta",
}
MAX_WORDS = 6
_DEVJUNK = re.compile(r"[a-z][A-Z]|\d|_|(?i:test|scene|faction|dialogue|marker|dummy|unused)")
PROPER = {"lugar", "personaje", "facción", "raza"}
# Palabras sueltas de mecánicas: solo cuentan si en el texto van con mayúscula ("Stamina", no "stamina")
MECHANIC_KINDS = {"habilidad", "mecánica"}
# Vocabulario básico de la traducción oficial que no sale como nombre propio en los plugins
EXTRA = [
    ("Fortify", "Reforzar"), ("Restore", "Restaurar"), ("Ravage", "Dañar"), ("Regenerate", "Regenerar"),
    ("Stamina", "Aguante"), ("Magicka", "Magia"), ("Health", "Salud"),
    ("Septim", "septim"), ("Septims", "septims"), ("Jarl", "jarl"), ("Thane", "thane"),
    ("Housecarl", "huscarle"), ("Dragon Soul", "alma de dragón"), ("Dragonborn", "Sangre de Dragón"),
]
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def build(data: Path) -> dict:
    official = json.load(gzip.open(data / "official.json.gz", "rt", encoding="utf-8"))
    pairs: dict[str, Counter] = defaultdict(Counter)
    kinds: dict[str, Counter] = defaultdict(Counter)
    for key, (en, es, _edid) in official.items():
        ftype = key.split("|")[2]
        rtype, field = ftype.split(" ")
        if field not in ("FULL", "TNAM", "SHRT") or rtype not in KINDS:
            continue
        if not en or not es:
            continue
        en, es = en.strip(), es.strip()
        if not en or len(en.split()) > MAX_WORDS:
            continue
        if en == es and (not en[:1].isupper() or _DEVJUNK.search(en)):
            continue  # palabra común idéntica o nombre interno de desarrollo: no aporta
        pairs[en][es] += 1
        kinds[en][KINDS[rtype]] += 1
    for en, es in EXTRA:
        pairs[en] = Counter({es: 99})
        kinds[en] = Counter({"mecánica": 99})
    out = []
    for en, c in pairs.items():
        es, n = c.most_common(1)[0]
        total = sum(c.values())
        out.append({
            "en": en, "es": es, "kind": kinds[en].most_common(1)[0][0], "count": total,
            "confidence": round(n / total, 2),
            "variants": [v for v, _ in c.most_common()[1:4]],
            "keep": es == en,   # nombre propio que se deja igual (p. ej. "Thalmor")
        })
    out.sort(key=lambda r: (-r["count"], r["en"]))
    path = data / "glossary.official.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"terminos": len(out), "ambiguos(<0.8)": sum(r["confidence"] < 0.8 for r in out),
            "por_tipo": Counter(r["kind"] for r in out).most_common()}


class Glossary:
    """Busca en un texto los términos del glosario (coincidencia más larga, sin distinguir mayúsculas)."""

    def __init__(self, entries: list[dict]):
        self.by_key = {}
        for r in entries:
            k = tuple(w.lower() for w in _WORD.findall(r["en"]))
            if k and (k not in self.by_key or r["count"] > self.by_key[k]["count"]):
                self.by_key[k] = r

    @classmethod
    def load(cls, data: Path) -> "Glossary":
        return cls(json.loads((data / "glossary.official.json").read_text(encoding="utf-8")))

    def find(self, text: str, limit: int = 40) -> list[dict]:
        orig = _WORD.findall(text)
        words = [w.lower() for w in orig]
        found, i = {}, 0
        while i < len(words):
            for n in range(min(MAX_WORDS, len(words) - i), 0, -1):
                r = self.by_key.get(tuple(words[i:i + n]))
                # Palabras sueltas: nombres propios, o mecánicas escritas con mayúscula
                if r and (n > 1 or r["kind"] in PROPER
                          or (r["kind"] in MECHANIC_KINDS and orig[i][:1].isupper())):
                    found[r["en"]] = r
                    i += n
                    break
            else:
                i += 1
        return list(found.values())[:limit]


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--data", default="data")
    f = sub.add_parser("find"); f.add_argument("--data", default="data"); f.add_argument("text")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        print(json.dumps(build(Path(a.data)), ensure_ascii=False, indent=1))
    else:
        for r in Glossary.load(Path(a.data)).find(a.text):
            print(f'{r["en"]} -> {r["es"]}  ({r["kind"]}, x{r["count"]}, conf {r["confidence"]})')


if __name__ == "__main__":
    main()
