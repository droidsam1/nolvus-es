# Nolvus ES — Nolvus Awakening 6 en español

Traducción al español (de España) de todo lo traducible en **Nolvus Awakening 6**:
objetos, hechizos, ventajas, misiones, diálogos, libros, mensajes y menús de los mods.

Objetivos:

- **Fiel al original.** Mantener el tono y el estilo de cada texto (un libro antiguo
  suena antiguo; un bandido no habla como un erudito) y la terminología oficial
  de la traducción de Bethesda.
- **Robusto ante actualizaciones.** No modifica ningún plugin de Nolvus. Las traducciones se
  inyectan en tiempo de ejecución con
  [Dynamic String Distributor (DSD)](https://www.nexusmods.com/skyrimspecialedition/mods/107676),
  así que si un mod se actualiza, lo que no ha cambiado sigue traducido y lo que cambia
  se detecta y se vuelve a traducir.
- **Reversible.** Todo va en un único mod de Mod Organizer: se activa o desactiva con una casilla.

## Estado

| Fase | Qué hace | Estado |
| --- | --- | --- |
| 1. Inventario | Extrae todos los textos de los plugins activos y mide cuánto hay en inglés | hecho ([informe](docs/INVENTARIO.md)) |
| 2. Español oficial | Recupera el texto oficial de Bethesda para registros del juego base que los mods dejan en inglés | hecho: 23.512 textos |
| 3. Traducciones existentes | Reutiliza traducciones al español ya publicadas en Nexus | hecho: 141.238 textos de 21 traducciones ([permisos](docs/PERMISOS.md)) |
| 4. Traducción con IA | Traduce el resto con Ollama, glosario y validación; reanudable | en curso |
| 5. Empaquetado | Genera el mod para MO2 (JSON de DSD + traducciones de MCM) | hecho |
| 6. Instalador | `INSTALAR.bat`: sin IA, guía las descargas de Nexus y lo monta todo | hecho |

Más detalle en [docs/PLAN.md](docs/PLAN.md).

## Instalar (jugadores)

No hace falta IA ni ninguna GPU especial: solo Nolvus Awakening 6 instalado y Python 3
(`winget install Python.Python.3.12`).

1. Descarga este repositorio (botón **Code → Download ZIP**) y descomprímelo.
2. Cierra Mod Organizer y doble clic en **`INSTALAR.bat`**. El instalador:
   - encuentra tu Nolvus y lee los textos de tus plugins (la primera vez, 20-40 min; se puede cortar y seguir);
   - saca el español oficial de Bethesda de tu propio juego;
   - te da los **enlaces directos** a las traducciones de otros autores en Nexus
     ([lista y permisos](docs/PERMISOS.md)). Las descargas tú; el instalador las encuentra en
     *Descargas*, las abre y comprueba registro a registro que son de tu versión de cada mod;
   - junta todo con las traducciones del proyecto (`traducciones/`) y crea los mods
     **Nolvus ES - Traduccion** y **Dynamic String Distributor**, y los activa con copia de seguridad de tu lista de mods.
3. Para quitarlo: **`DESINSTALAR.bat`**.

Opciones: `INSTALAR.bat --genero femenino` (traducciones que distinguen el sexo del personaje),
`--reescanear` (tras actualizar Nolvus), `--instancia "D:\Nolvus\Instances\Nolvus Awakening"`.

## Corregir traducciones

Las traducciones del proyecto están en [`traducciones/`](traducciones/LEEME.md), un archivo por plugin.
Se pueden corregir directamente en GitHub y enviar un *pull request*.

## Desarrollo

### Inventario (fase 1)

```bash
python -m nolvus_es.inventory extract --instance "C:/Nolvus/Instances/Nolvus Awakening" --out data
python -m nolvus_es.inventory report --out data
```

`extract` es reanudable: si se corta, la siguiente ejecución continúa donde lo dejó.
Las herramientas **solo leen** la instancia de Nolvus; todo lo que generan va a `data/` y `build/`.

### Traducir con IA (Ollama)

Doble clic en:

| Archivo | Para qué |
| --- | --- |
| `1_TRADUCIR.bat` | Empieza o continúa la traducción. Se puede cerrar o apagar el PC en cualquier momento. |
| `2_ESTADO.bat` | Progreso y tiempo estimado. |
| `3_PARAR.bat` | Para limpiamente al terminar los lotes en curso. |
| `4_EMPAQUETAR.bat` | Actualiza el mod en Mod Organizer con todo lo traducido hasta ahora. |
| `5_EXTRAER_TRADUCCIONES.bat` | Descomprime en `data/imports` las traducciones de Nexus descargadas. |

Para publicar lo traducido: `python -m nolvus_es.export --data data --out traducciones`.

Requisitos: Python 3 (`winget install Python.Python.3.12`) y Ollama con el modelo indicado en `1_TRADUCIR.bat`.
El estado vive en `data/trabajo.sqlite`; cada lote se guarda al terminar.
