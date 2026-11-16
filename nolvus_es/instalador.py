"""Instalador de Nolvus ES: traduce tu Nolvus al español sin IA ni modelos locales.

Pasos (unos minutos; se puede cortar y repetir):
  1. Encuentra tu instalación de Nolvus y su perfil.
  2. Saca el español oficial de Bethesda de tu propio juego y lo aplica a los registros que
     Nolvus deja en inglés (según catalogo/receta_oficial.json.gz: solo claves, sin texto).
  3. Descarga de Nexus las traducciones de otros autores: automáticamente si tienes cuenta Premium
     (clave en NEXUS.txt), o guiándote con enlaces directos si no. Luego las descomprime y
     comprueba registro a registro que son de tu versión de cada mod.
  4. Crea los mods "Nolvus ES - Traduccion" y "Dynamic String Distributor" en Mod Organizer
     y los activa (con copia de seguridad de tu lista de mods).

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


# ----------------------------------------------------------------- 2. español oficial

RECETA = REPO / "catalogo" / "receta_oficial.json.gz"


def oficial(inst: Instance, data: Path, destino: Path) -> int:
    """Español oficial de Bethesda (de los BSA del propio jugador) para las claves de la receta."""
    import gzip
    from . import official
    from .inventory import OFFICIAL
    from .phase2 import PACK_NAME
    dic = data / "official.json.gz"
    if not dic.exists():
        # Cada plugin oficial se lee de donde lo sirve MO2 (el Creation Club puede venir en un mod)
        resueltos = inst.resolve_plugins()
        grupos: dict[Path, list[str]] = {}
        # Todos los oficiales disponibles (el Creation Club se carga también sin estar en plugins.txt)
        orden = {m.lower(): i for i, m in enumerate(official.OFFICIAL_MASTERS)}
        for n in sorted((n for n in resueltos if OFFICIAL.match(n)), key=lambda n: (orden.get(n, 99), n)):
            ruta = Path(resueltos[n][0])
            grupos.setdefault(ruta.parent, []).append(ruta.name)
        off = {}
        for carpeta, nombres in grupos.items():
            tmp = data / "official.parcial.json.gz"
            official.build(carpeta, nombres, tmp)
            off.update(json.load(gzip.open(tmp, "rt", encoding="utf-8")))
            tmp.unlink()
        with gzip.open(dic, "wt", encoding="utf-8") as f:
            json.dump(off, f, ensure_ascii=False)
    off = json.load(gzip.open(dic, "rt", encoding="utf-8"))
    receta = json.load(gzip.open(RECETA, "rt", encoding="utf-8"))
    por_owner: dict[str, list] = {}
    for key, idx in receta:
        o = off.get(key)
        if not o or not o[1]:
            continue
        owner, local, ftype, _ = key.split("|")
        e = {"form_id": f"0x{local}|{owner}", "type": ftype, "string": o[1]}
        if idx is not None:
            e["index"] = idx
        por_owner.setdefault(owner, []).append(e)
    n = 0
    for owner, entries in por_owner.items():
        d = destino / "SKSE" / "Plugins" / "DynamicStringDistributor" / owner
        d.mkdir(parents=True, exist_ok=True)
        (d / PACK_NAME).write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        n += len(entries)
    return n


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


NEXUS_API = "https://api.nexusmods.com/v1"
NEXUS_TXT = REPO / "NEXUS.txt"


def clave_nexus() -> str | None:
    """Clave personal de Nexus (nexusmods.com → Settings → API Keys), en NEXUS.txt o NEXUS_API_KEY."""
    if os.environ.get("NEXUS_API_KEY"):
        return os.environ["NEXUS_API_KEY"].strip()
    if NEXUS_TXT.exists():
        for line in NEXUS_TXT.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.lower().startswith("clave=") and len(line) > 6:
                return line[6:].strip()
    return None


def _nexus(path: str, clave: str):
    import urllib.request
    req = urllib.request.Request(f"{NEXUS_API}{path}", headers={
        "apikey": clave, "Application-Name": "nolvus-es", "Application-Version": "1.0",
        "User-Agent": "nolvus-es/1.0 (github.com/droidsam1/nolvus-es)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def descargar_nexus(faltan: list[dict], clave: str, destino: Path) -> int:
    """Descarga automática con la API oficial de Nexus. Solo funciona con cuenta Premium
    (Nexus no da enlaces directos por API a las cuentas gratuitas)."""
    import urllib.parse
    import urllib.request
    try:
        u = _nexus("/users/validate.json", clave)
    except Exception as e:  # noqa: BLE001
        print(f"  La clave de Nexus no funciona ({e}). Sigo con las descargas manuales.")
        return 0
    if not u.get("is_premium"):
        print(f"  Hola, {u.get('name')}: tu cuenta de Nexus no es Premium, así que Nexus no permite "
              "descargar por API. Sigo con las descargas guiadas.")
        return 0
    destino.mkdir(parents=True, exist_ok=True)
    n = 0
    for a in faltan:
        try:
            links = _nexus(f"/games/{a.get('juego', 'skyrimspecialedition')}/mods/{a['nexus']}/files/"
                           f"{a['file_id']}/download_link.json", clave)
            uri = links[0]["URI"]
            nombre = urllib.parse.unquote(Path(urllib.parse.urlparse(uri).path).name)
            tmp = destino / (nombre + ".parcial")
            print(f"  descargando {nombre} …", flush=True)
            with urllib.request.urlopen(urllib.request.Request(uri, headers={"User-Agent": "nolvus-es/1.0"}),
                                        timeout=600) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            tmp.replace(destino / nombre)
            n += 1
            time.sleep(1)                      # sin prisas: respetar los límites de la API
        except Exception as e:  # noqa: BLE001
            print(f"  no se pudo descargar {a['nombre']}: {e}")
    return n


def carpetas_descarga(inst: Instance) -> list[Path]:
    """Descargas de Windows, la carpeta de descargas de Mod Organizer (botón «Mod manager download») e incluidos/."""
    out = [Path.home() / "Downloads", REPO / "incluidos"]
    ini = inst.root / "MO2" / "ModOrganizer.ini"
    try:
        for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("download_directory="):
                v = line.split("=", 1)[1].strip().replace("\\\\", "\\").replace("@ByteArray(", "").rstrip(")")
                if v:
                    out.append(Path(v))
    except OSError:
        pass
    out.append(inst.root / "MODS" / "downloads")
    return out


def necesarios(cat: dict, genero: str) -> list[dict]:
    return [a for a in cat["archivos"] if a.get("variante") in (None, genero)]


def guiar_descargas(cat: dict, genero: str, carpetas: list[Path], auto: bool) -> dict[int, Path]:
    lista = necesarios(cat, genero)
    clave = clave_nexus()
    if clave:
        destino = REPO / "instalacion" / "nexus"
        carpetas = carpetas + [destino]
        faltan = [a for a in lista if not localizar(a, carpetas)]
        if faltan:
            print(f"Descargando {len(faltan)} archivos con tu cuenta de Nexus…")
            descargar_nexus(faltan, clave, destino)
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


def importar(activos: dict[str, Path], extraidos: dict[int, Path], cat: dict, data: Path) -> dict:
    from .importer import import_pair
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
    nuevo = Path(tempfile.mkdtemp(prefix="nolvus-es-", dir=trabajo))

    titulo("1/4 Español oficial de Bethesda (de tu propio juego)")
    print(f"  {oficial(inst, data, trabajo / 'oficial'):,} textos".replace(",", "."), flush=True)
    resueltos = inst.resolve_plugins()
    activos = {n.lower(): resueltos[n.lower()][0] for n in inst.active_plugins() if n.lower() in resueltos}

    titulo("2/4 Traducciones de otros autores en Nexus")
    carpetas = [Path(p) for p in a.descargas] if a.descargas else carpetas_descarga(inst)
    hay = guiar_descargas(cat, a.genero, carpetas, a.si)
    sz = siete_zip(inst)
    extraidos = {}
    for fid, arch in hay.items():
        try:
            descomprimir(arch, trabajo / "descargas" / str(fid), sz)
            extraidos[fid] = trabajo / "descargas" / str(fid)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR al abrir {arch.name}: {e}")
    importar(activos, extraidos, cat, data)

    titulo("3/4 Creando el mod «Nolvus ES - Traduccion»")
    from .ensamblar import ensamblar
    from .espfile import read_header
    from .mcm import scan
    (data / "mcm_inventory.json").write_text(json.dumps(scan(inst), ensure_ascii=False, indent=1), encoding="utf-8")

    class Ligeros(dict):              # ¿plugin ESL? (solo se mira la cabecera de los que hacen falta)
        def get(self, name, default=False):
            if name not in self:
                p = activos.get(name.lower())
                self[name] = bool(p and read_header(Path(p)).is_light)
            return dict.get(self, name, default)

    stats = ensamblar(data, REPO / "data" / "traducciones", nuevo, trabajo / "oficial", Ligeros())
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

    titulo("4/4 Activando en Mod Organizer")
    if a.no_activar:
        print("  (sin tocar la lista de mods: --no-activar)")
        return
    if mo2_abierto():
        print("  Mod Organizer está abierto: ciérralo y vuelve a ejecutar INSTALAR.bat (lo demás ya está hecho).")
        return
    copia = activar(inst, [MOD_ES, MOD_DSD] if ok_dsd else [MOD_ES])
    print(f"  Activados. Copia de tu lista de mods anterior: {copia.name}")
    print("\nListo: abre Mod Organizer y lanza el juego. Para quitarlo: DESINSTALAR.bat")
    creditos(cat, set(extraidos), a.si)


def creditos(cat: dict, usados: set, auto: bool):
    """Agradecimiento a los autores, con sus enlaces. Respaldar (endorse) es siempre voluntario:
    el instalador nunca lo hace por el usuario ni lo exige."""
    lista = [a for a in cat["archivos"] if a["file_id"] in usados]
    if not lista:
        return
    titulo("Gracias a quienes lo han hecho posible")
    vistos = set()
    for a in lista:
        if (a["nexus"], a["autor"]) in vistos:
            continue
        vistos.add((a["nexus"], a["autor"]))
        print(f"  {a['mod']:<34} {a['autor']:<18} https://www.nexusmods.com/skyrimspecialedition/mods/{a['nexus']}")
    print("\nSi te gusta su trabajo, puedes respaldar (endorse) sus traducciones en Nexus: es la mejor forma de "
          "agradecerlo. (Nexus permite hacerlo pasados 15 minutos desde la descarga.)")
    if not auto and input("¿Abro sus páginas en el navegador? [s/N] ").strip().lower() in ("s", "si", "sí"):
        for nexus in sorted({a["nexus"] for a in lista}):
            webbrowser.open(f"https://www.nexusmods.com/skyrimspecialedition/mods/{nexus}")
            time.sleep(0.4)


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
    ap.add_argument("--si", action="store_true", help="no preguntar nada")
    ap.add_argument("--no-activar", action="store_true", help="crear los mods pero no tocar la lista de mods")
    a = ap.parse_args(argv)
    (cmd_instalar if a.orden == "instalar" else cmd_desinstalar)(a)


if __name__ == "__main__":
    main()
