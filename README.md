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

No hace falta IA, ni GPU especial, ni instalar nada más: solo Nolvus Awakening 6. Si no tienes
Python, el instalador prepara uno portátil (el oficial de python.org) solo para él.

1. Descarga este repositorio (botón **Code → Download ZIP**) y descomprímelo.
2. Cierra Mod Organizer y doble clic en **`INSTALAR.bat`**. El instalador:
   - encuentra tu Nolvus y saca el español oficial de Bethesda de tu propio juego;
   - te da los **enlaces directos** a las traducciones de otros autores en Nexus
     ([lista y permisos](docs/PERMISOS.md)). Las descargas tú; el instalador las encuentra en
     *Descargas*, las abre y comprueba registro a registro que son de tu versión de cada mod;
   - junta todo y crea los mods
     **Nolvus ES - Traduccion** y **Dynamic String Distributor**, y los activa con copia de seguridad de tu lista de mods.
3. Para quitarlo: **`DESINSTALAR.bat`**.

**Con cuenta Premium de Nexus, todo es automático:** copia `NEXUS.ejemplo.txt` como `NEXUS.txt` y pega
tu clave personal de Nexus (nexusmods.com → Settings → API Keys). El instalador descargará solo
las traducciones. Sin Premium, Nexus no permite descargar por API y el instalador te guía con enlaces.

Opciones: `INSTALAR.bat --genero femenino` (traducciones que distinguen el sexo del personaje),
`--instancia "D:\Nolvus\Instances\Nolvus Awakening"`.

## Qué hay (y qué no) en este repositorio

Solo código, la lista de enlaces a Nexus y documentación. **No contiene texto de ningún juego ni
de ningún mod**, ni traducciones de otros autores: el instalador las obtiene en tu PC a partir de
tu propio juego y de las descargas que haces tú desde Nexus. Ver [docs/PERMISOS.md](docs/PERMISOS.md).

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
| `6_TRADUCIR_API.bat` | Alternativa a Ollama: traduce lo pendiente con la API por lotes de Anthropic u OpenAI (clave en `API.txt`, que no se sube). Puede ir a la vez que Ollama. |

Requisitos: Python 3 (`winget install Python.Python.3.12`) y Ollama con el modelo indicado en `1_TRADUCIR.bat`.
El estado vive en `data/trabajo.sqlite`; cada lote se guarda al terminar.
