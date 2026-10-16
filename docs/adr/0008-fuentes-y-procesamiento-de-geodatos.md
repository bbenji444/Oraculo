# ADR-0008 — Fuentes y procesamiento de geodatos

- **Estado:** aceptado
- **Fecha:** 2026-10-15
- **Fase:** F1
- **Decide:** Benji

## Contexto

La Fase 1 construye el catálogo `regions` (ADR-0002) y los PMTiles del navegador (ADR-0004). Hay que fijar qué datos se usan y cómo se transforman, porque esas decisiones afectan la geolocalización de noticias (F4) y lo que ve el analista.

Datos verificados el 15 de octubre de 2026:

- **INEGI** publica el **"Marco Geoestadístico, Encuesta Intercensal 2025"** (edición 2026, cobertura del 31 de julio al 14 de noviembre de 2025) como un ZIP nacional de 2,946,855,741 bytes (`794551196649_s.zip`). El servidor acepta peticiones `Range`. Leyendo solo el índice del ZIP (3,373 bytes) se vio que contiene 32 ZIPs por estado y `MG_Integrado_Encuesta_Intercensal_2025.zip` (256 MB comprimido), con el marco nacional integrado. Proyección: Cónica Conforme de Lambert, datum ITRF2008, elipsoide GRS80.
- **Natural Earth** `ne_10m_admin_0_countries` (dominio público) tiene los nombres de países en español (`NAME_ES`). En algunos países (Francia, Noruega) el campo `ISO_A3` vale `-99`.
- PostgreSQL `unaccent` convierte la ñ en n (`Peñón` → `Penon`), según la prueba de integración de la Fase 0.

## Decisión

1. **Edición INEGI:** la más reciente (Encuesta Intercensal 2025). Se descarga **solo** el ZIP integrado nacional, leyendo con `Range` únicamente sus bytes dentro del ZIP grande (256 MB en lugar de 2.9 GB). Se verifica con el CRC del propio ZIP y se registra en `geodata/raw/MANIFIESTO.json` (URL, edición, fecha, tamaño y SHA-256).
2. **Países:** Natural Earth 1:10m.
   - Nombre en español desde `NAME_ES`.
   - Código desde `ISO_A3`, y `ADM0_A3` cuando `ISO_A3` vale `-99`.
3. **Geometría de México (país) = unión de los 32 estados de INEGI**, no el contorno de Natural Earth. Así la jerarquía es coherente: un punto en la costa que cae en un estado también cae en México. Las teselas de países usan la misma geometría de la base, para que el borde de México coincida con el de sus estados en el mapa.
4. **Punto representativo con `ST_PointOnSurface`** (columna `centroid`). El centroide geométrico de una forma cóncava o de media luna puede caer fuera del polígono, y el sistema nunca debe dibujar una noticia fuera de su región.
5. **Geometrías:** se reparan con `ST_MakeValid`. Si la reparación produce una colección mixta, se conservan solo los polígonos (`ST_CollectionExtract(…, 3)`) y se guardan como MultiPolygon. Se cargan a resolución completa; la simplificación se hace solo al generar PMTiles.
6. **Normalización de nombres:** una sola función de Python (`app.domain.names.normalize_name`): mayúsculas, sin acentos ni diéresis, **conservando la Ñ**, sin espacios repetidos. La usan el cargador, el buscador y el geocodificador. No se usa `unaccent` de PostgreSQL para `name_norm`.
7. **Alias:** se mantienen en `geodata/aliases.csv`, revisado por una persona. Incluye los alias de la especificación §11 y los nombres cortos con que los medios escriben los estados ("Coahuila", "Michoacán", "Veracruz").
8. **Población:** el Marco Geoestadístico no la incluye; queda `NULL` hasta que F4 decida si se carga el Censo 2020.

### Hallazgos durante la implementación (15 de octubre de 2026)

9. **GDAL no lee directamente de `/mnt/d`.** En el WSL de desarrollo (kernel 5.10), GDAL recibió bytes dañados al abrir un GeoJSON que `head`, `cat` y Python leían bien: 3 de 3 intentos fallaron, y el mismo archivo copiado a `/tmp` se leyó sin error. Con un shapefile, el mismo defecto podría corromper geometrías **sin dar error**. Por eso:
   - las capas se extraen del ZIP a una carpeta de trabajo en el disco de Linux (`GEODATA_WORK_DIR`, por defecto `~/.cache/monitor-noticias/geodata`), y `zipfile` verifica el CRC de cada archivo al extraerlo;
   - cualquier otra entrada se copia ahí y se compara su SHA-256 antes de usarla;
   - a `/mnt/d` solo van los resultados finales (PMTiles), copiados y verificados.
10. **Localidades en dos capas.** 46,894 localidades rurales amanzanadas vienen como polígono en `00l` y también como punto en `00lpr`, con la misma clave y el mismo nombre (`PLANO = "Si"`). Son la misma localidad: se cargan una sola vez, conservando el polígono. Total de localidades distintas: 296,850 (no 343,744). La validación comprueba ambos números.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Descargar el ZIP nacional completo (2.9 GB) | Trae manzanas, vialidades y AGEB que no se usan; 11 veces más datos. Queda como plan B si la descarga por `Range` falla. |
| Usar `ST_Centroid` | Puede caer fuera del polígono. |
| Contorno de México de Natural Earth | No coincide con los límites INEGI de los estados; generaría puntos "en un estado pero fuera del país". |
| `unaccent` para `name_norm` | Convierte la Ñ, contra la regla de CLAUDE.md §6.3. |
| Simplificar antes de cargar a PostGIS | Las consultas espaciales ("¿en qué municipio cae este punto?") perderían precisión en los bordes. |

## Consecuencias

- La descarga depende de que el servidor de INEGI siga aceptando `Range`; si deja de hacerlo, se usa el plan B.
- Al actualizar a una edición nueva de INEGI basta con cambiar la URL y la edición en `geodata/scripts/config.py` y volver a correr `make geo-load`: la carga es idempotente (`ON CONFLICT (code) DO UPDATE`).
- Las localidades sin polígono (localidades rurales puntuales) tienen `geom` nulo y solo `centroid`.
- Atribución obligatoria en mapas y reportes: © INEGI, Natural Earth, © colaboradores de OpenStreetMap (mapa base, ODbL) y Protomaps.
