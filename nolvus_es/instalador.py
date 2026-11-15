"""Instalador de Nolvus ES: traduce tu Nolvus al español sin IA ni modelos locales.

Pasos (se puede cortar y repetir: lo ya hecho no se repite):
  1. Encuentra tu instalación de Nolvus y su perfil.
  2. Lee los textos de todos tus plugins (la primera vez tarda un rato).
  3. Saca el español oficial de Bethesda de tu propio juego.
  4. Te guía para descargar de Nexus las traducciones de otros autores (enlaces directos);
     cuando las tienes en Descargas, las descomprime y comprueba registro a registro que
     corresponden a tu versión de cada mod.
  5. Junta todo con las traducciones del proyecto (carpeta traducciones/) y crea el mod
     "Nolvus ES - Traduccion" + "Dynamic String Distributor" en Mod Organizer.
  6. Los activa en tu lista de mods (con copia de seguridad), si Mod Organizer está cerrado.

Uso:
    python -m nolvus_es.instalador                 (lo normal: INSTALAR.bat)
    python -m nolvus_es.instalador desinstalar     (DESINSTALAR.bat)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
import time
import webbrowser
import zipfile
from pathlib import Path
from types import SimpleNamespace

from .mo2 import Instance

REPO = Path(__file__).resolve().parent.parent
CATALOGO = REPO / "catalogo" / "traducciones_nexus.json"
MOD_ES = "Nolvus ES - Traduccion"
MOD_DSD = "Dynamic String Distributor"
ARCHIVOS = (".7z", ".rar", ".zip")


def titulo(t: str):
    print(f"\n=== {t} ===", flush=True)


def preguntar(texto: str, auto: bool, defecto: bool = True) -> bool:
    if auto:
        return defecto
    r = input(f"{texto} [{'S/n' if defecto else 's/N'}] ").strip().lower()
    return defecto if not r else r.startswith("s")


# ----------------------------------------------------------------- 1. instalación

def buscar_instancias() -> list[Path]:
    raices = []
    if os.name == "nt":
        raices = [Path(f"{d}:\\") for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    found = []
    for r in raices:
        base = r / "Nolvus" / "Instances"
        if base.exists():
            for inst in sorted(base.iterdir()):
                if (inst / "MO2" / "ModOrganizer.exe").exists():
                    found.append(inst)
    return found


def elegir_perfil(root: Path, pedido: str | None) -> str:
    perfiles = sorted(p.name for p in (root / "MODS" / "profiles").iterdir() if p.is_dir())
    if pedido:
        if pedido not in perfiles:
            sys.exit(f"No existe el perfil '{pedido}'. Perfiles: {', '.join(perfiles)}")
        return pedido
    for p in perfiles:
        if p.lower() == root.name.lower():
            return p
    return perfiles[0]


def mo2_abierto() -> bool:
    if os.name != "nt":
        return False
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ModOrganizer.exe"], capture_output=True, text=True)
    return "ModOrganizer.exe" in r.stdout


# ----------------------------------------------------------------- 2-3. inventario y oficial

def inventario(inst: Instance, data: Path):
    from .inventory import extract
    args = SimpleNamespace(instance=str(inst.root), profile=inst.profile, out=str(data), budget=60)
    while True:
        extract(args)
        st = json.loads((data / "plugins.json").read_text(encoding="utf-8"))
        if all(p["done"] for p in st["plugins"]):
            return st


def oficial(inst: Instance, data: Path, st: dict, build: Path) -> dict:
    from . import official, phase2
    if not (data / "official.json.gz").exists():
        names = [p["name"] for p in st["plugins"] if (p.get("summary") or {}).get("official")]
        official.build(inst.game_data, names, data / "official.json.gz")
    if build.exists():
        shutil.rmtree(build)
    return phase2.run(data, build)


# ----------------------------------------------------------------- 4. traducciones de Nexus

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def localizar(archivo: dict, carpetas: list[Path]) -> Path | None:
    nombre, mid = _norm(archivo["nombre"]), str(archivo["nexus"])
    mejor = None
    for c in carpetas:
        if not c.exists():
            continue
        for f in c.iterdir():
            if not f.is_file() or not f.name.lower().endswith(ARCHIVOS):
                continue
            n = _norm(f.name)
            if n.startswith(nombre) and re.match(rf"[\s\-_.]*{mid}(?!\d)", n[len(nombre):]):
                if mejor is None or f.stat().st_mtime > mejor.stat().st_mtime:
                    mejor = f
    return mejor


def necesarios(cat: dict, genero: str) -> list[dict]:
    return [a for a in cat["archivos"] if a.get("variante") in (None, genero)]


def guiar_descargas(cat: dict, genero: str, carpetas: list[Path], auto: bool) -> dict[int, Path]:
    lista = necesarios(cat, genero)
    while True:
        hay = {a["file_id"]: localizar(a, carpetas) for a in lista}
        faltan = [a for a in lista if not hay[a["file_id"]]]
        print(f"Tienes {len(lista) - len(faltan)} de {len(lista)} archivos.")
        if not faltan or auto:
            return {k: v for k, v in hay.items() if v}
        print("\nFaltan estas descargas (botón «Manual download» o «Mod manager download» → guarda el archivo en Descargas):")
        for i, a in enumerate(faltan, 1):
            print(f"  {i:>2}. {a['mod']:<34} {a['nombre']}  (v{a['version']}, de {a['autor']})")
            print(f"      {a['url']}")
        r = input("\n[A] abrir los enlaces en el navegador · [Enter] volver a comprobar · [C] continuar sin ellas: ").strip().lower()
        if r == "a":
            for a in faltan:
                webbrowser.open(a["url"])
                time.sleep(0.4)
        elif r == "c":
            return {k: v for k, v in hay.items() if v}


def siete_zip(inst: Instance) -> str | None:
    for p in (inst.root.parent.parent / "lib" / "7z.exe", Path(r"C:\Program Files\7-Zip\7z.exe")):
        if p.exists():
            return str(p)
    return shutil.which("7z")


def descomprimir(archivo: Path, destino: Path, sz: str | None) -> str:
    marca = destino / ".extraido"
    if marca.exists() and marca.read_text(encoding="utf-8") == archivo.name:
        return "ya estaba"
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    if archivo.suffix.lower() == ".zip":
        with zipfile.ZipFile(archivo) as z:
            z.extractall(destino)
    elif sz:
        r = subprocess.run([sz, "x", "-y", f"-o{destino}", str(archivo)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[-300:])
    else:
        raise RuntimeError("no encuentro 7-Zip para abrir .7z/.rar")
    marca.write_text(archivo.name, encoding="utf-8")
    return "descomprimido"


def importar(st: dict, extraidos: dict[int, Path], cat: dict, data: Path) -> dict:
    from .importer import import_pair
    activos = {p["name"].lower(): p["path"] for p in st["plugins"] if p.get("path")}
    por_id = {a["file_id"]: a for a in cat["archivos"]}
    hecho = {}
    hechos_file = data / "tm" / "importados.json"
    if hechos_file.exists():
        hecho = json.loads(hechos_file.read_text(encoding="utf-8"))
    resumen = {}
    for fid, carpeta in extraidos.items():
        a = por_id[fid]
        for f in sorted(carpeta.rglob("*")):
            if f.suffix.lower() not in (".esp", ".esm", ".esl") or not f.is_file():
                continue
            orig = activos.get(f.name.lower())
            if not orig:
                continue
            marca = f"{f.stat().st_size}:{f.stat().st_mtime_ns}:{Path(orig).stat().st_mtime_ns}"
            if hecho.get(f.name) == marca:
                continue
            r = import_pair(Path(orig), f, f"nexus:{a['nexus']}", data / "tm")
            resumen[f.name] = r.get("ok", 0)
            hecho[f.name] = marca
            print(f"  {f.name:<45} {r.get('ok', 0):>6} textos aplicables  ({a['mod']})", flush=True)
    hechos_file.parent.mkdir(parents=True, exist_ok=True)
    hechos_file.write_text(json.dumps(hecho, ensure_ascii=False, indent=1), encoding="utf-8")
    return resumen


def dsd_de_terceros(extraidos: dict[int, Path], destino: Path) -> int:
    """Archivos que ya vienen en formato DSD (p. ej. Vigilant Book Covers): se copian tal cual."""
    n = 0
    for carpeta in extraidos.values():
        for f in carpeta.rglob("*.json"):
            parts = [p.lower() for p in f.parts]
            if "dynamicstringdistributor" in parts:
                i = parts.index("dynamicstringdistributor")
                rel = Path("SKSE", "Plugins", "DynamicStringDistributor", *f.parts[i + 1:])
                (destino / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, destino / rel)
                n += 1
    return n


def menus_de_terceros(extraidos: dict[int, Path], destino: Path, data: Path) -> int:
    """Menús MCM traducidos por humanos (Interface/Translations/*_SPANISH.txt): sustituyen a los nuestros,
    clave a clave y solo si el mod está instalado; lo que no cubren se queda con la traducción del proyecto."""
    from .mcm import read_translation_file
    inv = {}
    mi = data / "mcm_inventory.json"
    if mi.exists():
        inv = {t["file"]: t for t in json.loads(mi.read_text(encoding="utf-8"))["translations"]}
    n = 0
    for carpeta in extraidos.values():
        for f in carpeta.rglob("*"):
            if not f.is_file() or not f.name.lower().endswith("_spanish.txt"):
                continue
            if [p.lower() for p in f.parts[-3:-1]] != ["interface", "translations"]:
                continue
            t = inv.get(f.name[: -len("_spanish.txt")].lower())
            if not t:
                continue
            try:
                en, es = read_translation_file(Path(t["path_english"])), read_translation_file(f)
            except OSError:
                continue
            if not en or not any(k in es for k in en):
                continue
            tdir = destino / "Interface" / "translations"
            tdir.mkdir(parents=True, exist_ok=True)
            nuestra = {}
            for old in list(tdir.iterdir()):              # nuestra versión (IA) de ese menú, si la hay
                if old.name.lower() == f.name.lower():
                    nuestra = read_translation_file(old)
                    old.unlink()
            # Por clave: traducción humana > la nuestra > inglés (claves nuevas del mod)
            lines = [f"{k}\t{es.get(k) or nuestra.get(k) or v}" for k, v in en.items()]
            (tdir / (Path(t["path_english"]).name[: -len("english.txt")] + "SPANISH.txt")).write_text(
                "\r\n".join(lines) + "\r\n", encoding="utf-16")
            n += 1
    return n


def instalar_dsd(extraidos: dict[int, Path], inst: Instance) -> bool:
    origen = extraidos.get(812636) or (REPO / "incluidos" / "DSD" if (REPO / "incluidos" / "DSD").exists() else None)
    dll = next(origen.rglob("DynamicStringDistributor.dll"), None) if origen else None
    if not dll:
        return False
    dest = inst.mods_dir / MOD_DSD
    plug = dest / "SKSE" / "Plugins"
    plug.mkdir(parents=True, exist_ok=True)
    for f in dll.parent.glob("DynamicStringDistributor.*"):
        shutil.copyfile(f, plug / f.name)
    (dest / "meta.ini").write_text("[General]\ngameName=SkyrimSE\nmodid=107676\nversion=1.5.2\n"
                                   "comments=Dynamic String Distributor, de SkyHorizon3 (GPL-3.0)\n", encoding="utf-8")
    return True


# ----------------------------------------------------------------- 6. lista de mods

def _modlist(inst: Instance) -> Path:
    return inst.profile_dir / "modlist.txt"


def activar(inst: Instance, mods: list[str]) -> Path:
    ml = _modlist(inst)
    lines = ml.read_text(encoding="utf-8-sig").splitlines()
    copia = ml.with_name(f"modlist.antes-nolvus-es-{time.strftime('%Y%m%d-%H%M%S')}.txt")
    shutil.copyfile(ml, copia)
    head = [l for l in lines if l.startswith("#")]
    rest = [l for l in lines if not l.startswith("#") and l[1:] not in mods]
    # En modlist.txt la primera línea es la de MÁS prioridad: nuestros mods arriba del todo.
    new = head + [f"+{m}" for m in mods] + rest
    ml.write_text("\n".join(new) + "\n", encoding="utf-8")
    return copia


def desactivar(inst: Instance, mods: list[str]) -> bool:
    ml = _modlist(inst)
    lines = ml.read_text(encoding="utf-8-sig").splitlines()
    new = [("-" + l[1:]) if l[:1] == "+" and l[1:] in mods else l for l in lines]
    if new != lines:
        shutil.copyfile(ml, ml.with_name(f"modlist.antes-desinstalar-nolvus-es-{time.strftime('%Y%m%d-%H%M%S')}.txt"))
        ml.write_text("\n".join(new) + "\n", encoding="utf-8")
        return True
    return False


# ----------------------------------------------------------------- órdenes

def _instancia(a) -> Instance:
    if a.instancia:
        root = Path(a.instancia)
    else:
        cands = buscar_instancias()
        if not cands:
            sys.exit("No encuentro ninguna instalación de Nolvus (X:\\Nolvus\\Instances\\...). "
                     "Indica la carpeta con --instancia \"C:\\Nolvus\\Instances\\Nolvus Awakening\".")
        root = cands[0]
        if len(cands) > 1 and not a.si:
            for i, c in enumerate(cands, 1):
                print(f"  {i}. {c}")
            root = cands[int(input("¿Cuál? ") or 1) - 1]
    inst = Instance(root, elegir_perfil(root, a.perfil))
    print(f"Nolvus: {inst.root}  (perfil «{inst.profile}»)")
    return inst


def cmd_instalar(a):
    inst = _instancia(a)
    trabajo = Path(a.trabajo) if a.trabajo else REPO / "instalacion"
    data = trabajo / "datos"
    data.mkdir(parents=True, exist_ok=True)
    cat = json.loads(CATALOGO.read_text(encoding="utf-8"))

    titulo("1/5 Leyendo los textos de tus plugins (la primera vez, 20-40 min; se puede cortar y seguir)")
    if a.reescanear and (data / "plugins.json").exists():
        (data / "plugins.json").unlink()
    st = inventario(inst, data)

    titulo("2/5 Español oficial de Bethesda (de tu propio juego)")
    r = oficial(inst, data, st, trabajo / "oficial")
    print(f"  {r.get('textos_oficiales', r)}" if isinstance(r, dict) else r)
    from .mcm import scan
    (data / "mcm_inventory.json").write_text(json.dumps(scan(inst), ensure_ascii=False, indent=1), encoding="utf-8")

    titulo("3/5 Traducciones de otros autores en Nexus")
    carpetas = [Path(p) for p in a.descargas] if a.descargas else [Path.home() / "Downloads", REPO / "incluidos"]
    hay = guiar_descargas(cat, a.genero, carpetas, a.si)
    sz = siete_zip(inst)
    extraidos = {}
    for fid, arch in hay.items():
        try:
            descomprimir(arch, trabajo / "descargas" / str(fid), sz)
            extraidos[fid] = trabajo / "descargas" / str(fid)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR al abrir {arch.name}: {e}")
    importar(st, extraidos, cat, data)

    titulo("4/5 Creando el mod «Nolvus ES - Traduccion»")
    from .ensamblar import ensamblar
    nuevo = Path(tempfile.mkdtemp(prefix="nolvus-es-", dir=trabajo))
    stats = ensamblar(data, REPO / "traducciones", nuevo, trabajo / "oficial")
    stats["dsd_de_terceros"] = dsd_de_terceros(extraidos, nuevo)
    stats["menus_de_terceros"] = menus_de_terceros(extraidos, nuevo, data)
    (nuevo / "meta.ini").write_text("[General]\ngameName=SkyrimSE\nmodid=0\nversion=1.0\n"
                                    "comments=Traducción al español de Nolvus (github.com/droidsam1/nolvus-es)\n",
                                    encoding="utf-8")
    destino = inst.mods_dir / MOD_ES
    if destino.exists():
        shutil.rmtree(destino)
    shutil.move(str(nuevo), destino)
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    ok_dsd = instalar_dsd(extraidos, inst) or (inst.mods_dir / MOD_DSD / "SKSE").exists()
    if not ok_dsd:
        print("  AVISO: falta Dynamic String Distributor; sin él el juego no carga las traducciones.")

    titulo("5/5 Activando en Mod Organizer")
    if a.no_activar:
        print("  (sin tocar la lista de mods: --no-activar)")
        return
    if mo2_abierto():
        print("  Mod Organizer está abierto: ciérralo y vuelve a ejecutar INSTALAR.bat (lo demás ya está hecho).")
        return
    copia = activar(inst, [MOD_ES, MOD_DSD] if ok_dsd else [MOD_ES])
    print(f"  Activados. Copia de tu lista de mods anterior: {copia.name}")
    print("\nListo: abre Mod Organizer y lanza el juego. Para quitarlo: DESINSTALAR.bat")


def cmd_desinstalar(a):
    inst = _instancia(a)
    if mo2_abierto():
        sys.exit("Cierra Mod Organizer y vuelve a ejecutar DESINSTALAR.bat.")
    if desactivar(inst, [MOD_ES, MOD_DSD]):
        print("Desactivados «Nolvus ES - Traduccion» y «Dynamic String Distributor».")
    if (inst.mods_dir / MOD_ES).exists() and preguntar("¿Borrar también la carpeta del mod de traducción?", a.si):
        shutil.rmtree(inst.mods_dir / MOD_ES)
    print("Tu Nolvus vuelve a estar como antes de instalar la traducción.")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Instalador de Nolvus ES")
    ap.add_argument("orden", nargs="?", default="instalar", choices=["instalar", "desinstalar"])
    ap.add_argument("--instancia", help='p. ej. "C:\\Nolvus\\Instances\\Nolvus Awakening"')
    ap.add_argument("--perfil")
    ap.add_argument("--genero", choices=["masculino", "femenino"], default="masculino",
                    help="variante de las traducciones que distinguen el sexo del personaje")
    ap.add_argument("--descargas", nargs="*", help="carpetas donde buscar las descargas de Nexus")
    ap.add_argument("--trabajo", help="carpeta de trabajo (por defecto, instalacion/ junto al instalador)")
    ap.add_argument("--reescanear", action="store_true", help="volver a leer los plugins (tras actualizar Nolvus)")
    ap.add_argument("--si", action="store_true", help="no preguntar nada")
    ap.add_argument("--no-activar", action="store_true", help="crear los mods pero no tocar la lista de mods")
    a = ap.parse_args(argv)
    (cmd_instalar if a.orden == "instalar" else cmd_desinstalar)(a)


if __name__ == "__main__":
    main()
