# Traducciones existentes (fase 3)

Revisión del 15-11-2026 de las traducciones al español (España) publicadas en Nexus para los
mods de Nolvus con más texto. "Versión Nolvus" es la que hay instalada; la traducción se
importa registro a registro y solo se usa directamente donde el registro no ha cambiado.

| Mod (versión Nolvus) | % del texto | Traducción elegida | Versión trad. | Encaje |
| --- | ---: | --- | --- | --- |
| Interesting NPCs 3DNPC (4.54) | 24,6 % | [56508](https://www.nexusmods.com/skyrimspecialedition/mods/56508) linqueo · alternativa revisada [101657](https://www.nexusmods.com/skyrimspecialedition/mods/101657) | 4.54 / 4.5.1 | exacta |
| Legacy of the Dragonborn (5.6.5) | 12,4 % | [20416](https://www.nexusmods.com/skyrimspecialedition/mods/20416) linqueo (buscar archivo antiguo 5.6.x) · [125182](https://www.nexusmods.com/skyrimspecialedition/mods/125182) Zedox | 6.10 | **otra versión** (v6) |
| Beyond Skyrim - Bruma (1.6.3) | 4,9 % | [40020](https://www.nexusmods.com/skyrimspecialedition/mods/40020) eslizon · [98644](https://www.nexusmods.com/skyrimspecialedition/mods/98644) definitiva | 1.6.3 / 1.6.4 | exacta |
| Remiel (1.7.5) | 3,7 % | [99307](https://www.nexusmods.com/skyrimspecialedition/mods/99307) | 1.7.6 | cercana |
| Inigo (2.4C) | 3,4 % | [169755](https://www.nexusmods.com/skyrimspecialedition/mods/169755) Iguano | 2.4C | exacta |
| Vigilant (1.7.3) | 2,3 % | [67225](https://www.nexusmods.com/skyrimspecialedition/mods/67225) (incluye voces) | 1.8.2 | cercana |
| Katana (3.0.5) | 2,3 % | [151442](https://www.nexusmods.com/skyrimspecialedition/mods/151442) | 3.0.5 | exacta |
| Falskaar (2.2) | 1,9 % | [11547](https://www.nexusmods.com/skyrimspecialedition/mods/11547) Petermsi | 2.2 | exacta |
| Lucien (1.6.3) | 1,7 % | [31886](https://www.nexusmods.com/skyrimspecialedition/mods/31886) | 1.7.2 | cercana |
| Wyrmstooth (1.20.2) | 1,4 % | [45596](https://www.nexusmods.com/skyrimspecialedition/mods/45596) | 1.20.3 | cercana |
| BS Bruma - LOTD Synergy (1.12) | 1,1 % | [87636](https://www.nexusmods.com/skyrimspecialedition/mods/87636) | 1.12 | exacta |
| The Forgotten City (1.8) | 1,1 % | [21283](https://www.nexusmods.com/skyrimspecialedition/mods/21283) (diferenciada por sexos) | 1.8b | exacta |
| Unslaad - LOTD patch (1.2) | 1,0 % | [57613](https://www.nexusmods.com/skyrimspecialedition/mods/57613) | 1.3 | cercana |
| Unslaad (3.0.2) | 1,0 % | [67222](https://www.nexusmods.com/skyrimspecialedition/mods/67222) | 3.0.6 | cercana |
| Vigilant - Book Covers (1.5) | 0,8 % | [163778](https://www.nexusmods.com/skyrimspecialedition/mods/163778) | 1.5 | exacta |
| The Wheels of Lull (5.1.13.3) | 0,8 % | [125480](https://www.nexusmods.com/skyrimspecialedition/mods/125480) Zedox | 5.1.13.3 | exacta |
| Ordinator (9.31) | 0,8 % | [3472](https://www.nexusmods.com/skyrimspecialedition/mods/3472) linqueo | 9.31.0 | exacta |
| Carved Brink (1.1) | 0,7 % | [32849](https://www.nexusmods.com/skyrimspecialedition/mods/32849) | 1.1 | exacta |
| Thaumaturgy (1.4.5) | 0,7 % | [57186](https://www.nexusmods.com/skyrimspecialedition/mods/57186) | 1.5 | cercana |
| Clockwork (1.0) | 0,6 % | [125343](https://www.nexusmods.com/skyrimspecialedition/mods/125343) Zedox | 1.0 | exacta |
| Auri (2.2) | 0,6 % | [178421](https://www.nexusmods.com/skyrimspecialedition/mods/178421) | 2.2 | exacta |
| Wintersun (3.2) | 0,5 % | [22563](https://www.nexusmods.com/skyrimspecialedition/mods/22563) linqueo | 3.2.0 | exacta |

Sin traducción encontrada: Citizens of Tamriel, Project AHO (parche limpio), Midwood Isle - CTD and
Main Quest Fixes, YOT - Your Own Thoughts.

## Cómo se importan

1. Instalar cada traducción en Mod Organizer **y dejarla desactivada** (solo se leen sus archivos).
2. `python -m nolvus_es.importer --sources sources.json`
3. Cada texto queda como `ok` (registro idéntico a tu versión: se usa) o `referencia`
   (la traducción es de otra versión: solo guía a la IA).

## Pendiente
- En el empaquetado, usar FormID corto para plugins `.esp` marcados como ESL.
