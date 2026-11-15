"""Lectura de una instancia de Mod Organizer 2 (perfil, mods activos y plugins activos).

Resuelve qué archivo físico "gana" para cada plugin, igual que hace el sistema
de archivos virtual de MO2: los mods más abajo en el panel izquierdo
(más arriba en modlist.txt) tienen prioridad.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PLUGIN_EXT = (".esp", ".esm", ".esl")


@dataclass
class Instance:
    root: Path          # ...\Nolvus Awakening
    profile: str        # "Nolvus Awakening"

    @property
    def mods_dir(self) -> Path:
        return self.root / "MODS" / "mods"

    @property
    def profile_dir(self) -> Path:
        return self.root / "MODS" / "profiles" / self.profile

    @property
    def game_data(self) -> Path:
        return self.root / "STOCK GAME" / "Data"

    @property
    def overwrite(self) -> Path:
        return self.root / "MODS" / "overwrite"

    def enabled_mods(self) -> list[str]:
        """Mods activos ordenados de MENOR a MAYOR prioridad."""
        lines = (self.profile_dir / "modlist.txt").read_text(encoding="utf-8").splitlines()
        mods = [l[1:] for l in lines if l.startswith("+") and not l.endswith("_separator")]
        return list(reversed(mods))

    def active_plugins(self) -> list[str]:
        """Plugins activos en orden de carga (los maestros de Bethesda incluidos)."""
        lines = (self.profile_dir / "plugins.txt").read_text(encoding="utf-8").splitlines()
        active = [l[1:] for l in lines if l.startswith("*")]
        order_file = self.profile_dir / "loadorder.txt"
        if order_file.exists():
            order = [l.strip() for l in order_file.read_text(encoding="utf-8").splitlines()
                     if l.strip() and not l.startswith("#")]
            aset = {p.lower() for p in active}
            implicit = [p for p in order if p.lower() not in aset and p.lower().endswith((".esm",))]
            # loadorder.txt incluye los maestros implícitos (Skyrim.esm, DLC, CC)
            act_or_implicit = aset | {p.lower() for p in implicit}
            return [p for p in order if p.lower() in act_or_implicit]
        return active

    def resolve_plugins(self) -> dict[str, tuple[Path, str]]:
        """plugin (minúsculas) -> (ruta física ganadora, nombre del mod o 'STOCK GAME')."""
        found: dict[str, tuple[Path, str]] = {}
        if self.game_data.exists():
            for name in os.listdir(self.game_data):
                if name.lower().endswith(PLUGIN_EXT):
                    found[name.lower()] = (self.game_data / name, "STOCK GAME")
        for mod in self.enabled_mods():
            d = self.mods_dir / mod
            for name in _listdir(str(d)):
                if name.lower().endswith(PLUGIN_EXT):
                    found[name.lower()] = (d / name, mod)
        if self.overwrite.exists():
            for name in os.listdir(self.overwrite):
                if name.lower().endswith(PLUGIN_EXT):
                    found[name.lower()] = (self.overwrite / name, "Overwrite")
        return found

    def find_loose_file(self, rel: str) -> Path | None:
        """Busca un archivo suelto (p.ej. Strings\\x_spanish.strings) siguiendo la prioridad de MO2."""
        rel_parts = rel.replace("\\", "/").split("/")
        candidates = [self.overwrite] + [self.mods_dir / m for m in reversed(self.enabled_mods())] + [self.game_data]
        for base in candidates:
            p = _ci_join(base, rel_parts)
            if p:
                return p
        return None


@lru_cache(maxsize=None)
def _listdir(path: str) -> tuple[str, ...]:
    try:
        return tuple(os.listdir(path))
    except OSError:
        return ()


def _ci_join(base: Path, parts: list[str]) -> Path | None:
    cur = base
    for part in parts:
        entries = _listdir(str(cur))
        if not entries:
            return None
        match = next((e for e in entries if e.lower() == part.lower()), None)
        if match is None:
            return None
        cur = cur / match
    return cur
