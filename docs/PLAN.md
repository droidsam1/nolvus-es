# Plan técnico

## Principios

1. **Nunca tocar Nolvus.** Ni plugins, ni BSA, ni el orden de carga. El resultado es un mod
   independiente que se coloca al final de la lista de MO2.
2. **Cada texto se identifica por su registro, no por su posición.** Clave estable:
   `plugin dueño | FormID | tipo de registro | campo | índice` (+ EditorID como respaldo).
   Así, si un mod se actualiza, solo cambian las claves cuyo texto original cambió.
3. **Memoria de traducción con huella del original.** Cada traducción guarda el texto inglés
   del que salió. Si el original cambia, la entrada queda marcada como obsoleta y se retraduce;
   si no cambia, se reutiliza tal cual.
4. **Prioridad de fuentes** (de más a menos fiable):
   1. Texto oficial de Bethesda en español (para registros del juego base que un mod sobrescribe).
   2. Traducciones al español publicadas por la comunidad.
   3. Traducción con IA siguiendo el glosario y revisión automática.
5. **Validación antes de empaquetar.** Ningún texto entra en el mod si rompe etiquetas
   (`<mag>`, `<dur>`, `<Alias=...>`, `[PageBreak]`, HTML de libros, `%s`, `\n`...).

## Fases

### 1. Inventario
- Lee el perfil de MO2 (`modlist.txt`, `plugins.txt`, `loadorder.txt`) y resuelve qué archivo
  físico gana para cada plugin.
- Extrae los campos traducibles (FULL, DESC, textos de libros, objetivos y diario de misión,
  líneas de diálogo, botones de mensajes, títulos de facciones...).
- Clasifica cada texto (español / inglés / nombre corto / neutro) y produce un informe.

### 2. Español oficial (sin IA)
Muchos mods (por ejemplo el Parche No Oficial) sobrescriben registros de `Skyrim.esm` y DLC
con su texto en inglés. Para esos registros se usa el texto oficial en español de las tablas
`.STRINGS` de Bethesda, buscado por FormID. Es exacto y coherente con el resto del juego.

### 3. Traducciones existentes
Importar traducciones al español publicadas (formato xTranslator/SST, DSD o ESP traducido)
y convertirlas a la memoria de traducción, comprobando que el texto original coincide.

### 4. Traducción con IA
- **Glosario** construido desde el juego oficial: nombres de lugares, razas, facciones,
  objetos y términos de mecánicas (p. ej. *Whiterun → Carrera Blanca*, *Thu'um*, *Dovahkiin*).
- **Contexto** por lote: tipo de registro, mod de origen, EditorID y textos vecinos
  (una línea de diálogo se traduce con las de su conversación).
- **Estilo:** registro y tono del original; libros con su voz; nada de modernismos.
- **Protección de marcadores:** se sustituyen por fichas antes de traducir y se restauran después.
- **Revisión:** segunda pasada que comprueba glosario, marcadores, longitud razonable y coherencia.
- Motor intercambiable: API o modelo local (Ollama).

### 5. Empaquetado
- `SKSE/Plugins/DynamicStringDistributor/<plugin>/nolvus-es.json` por cada plugin.
- `Interface/translations/<mod>_SPANISH.txt` para menús MCM.
- Informe de cobertura y lista de textos no traducibles por esta vía (texto dentro de scripts).

### 6. Actualizaciones
Volver a ejecutar el inventario tras actualizar Nolvus: se comparan huellas, se retraduce
solo lo nuevo o cambiado y se regenera el paquete.

## Límites conocidos
- Las voces de personajes añadidos por mods siguen en inglés (solo se traducen subtítulos).
- Textos escritos dentro de scripts Papyrus o de DLLs no se cubren con DSD.
- Uso personal: redistribuir traducciones de mods ajenos requiere permiso de cada autor.
