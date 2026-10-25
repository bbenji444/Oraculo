# Registros de decisiones de arquitectura (ADR)

Cada archivo documenta **una** decisión importante: el contexto, lo que se decidió, las alternativas y sus consecuencias.
Sirven para que alguien nuevo entienda *por qué* el proyecto es como es, no solo *cómo*.

## Reglas

- Nombre: `NNNN-titulo-en-minusculas.md`, numeración consecutiva.
- Secciones obligatorias: Contexto, Decisión, Alternativas consideradas y Consecuencias.
- Un ADR aceptado no se reescribe: si la decisión cambia, se crea uno nuevo que lo reemplaza y se marca el anterior como "reemplazado por ADR-XXXX".
- Cualquier cambio a la tabla de stack de la especificación (sección 5.4) requiere un ADR.

## Índice

| ADR | Título | Estado |
|---|---|---|
| [0001](0001-arquitectura-hexagonal-e-idioma.md) | Arquitectura hexagonal y convención de idioma | Aceptado |
| [0002](0002-postgis-y-catalogo-regions-inegi.md) | PostgreSQL + PostGIS y catálogo `regions` con claves INEGI | Aceptado |
| [0003](0003-estrategia-multiproveedor-noticias.md) | Estrategia multiproveedor de noticias | Aceptado |
| [0004](0004-maplibre-globo-y-pmtiles.md) | MapLibre GL (globo) + PMTiles autoalojados | Aceptado |
| [0005](0005-celery-redis-procesamiento-asincrono.md) | Celery + Redis para procesamiento asíncrono | Aceptado |
| [0006](0006-entorno-desarrollo-sin-docker.md) | Entorno de desarrollo sin Docker: servicios nativos en WSL | Aceptado |
| [0007](0007-maplibre-v6.md) | MapLibre GL JS v6 en lugar de v5 | Aceptado |
| [0008](0008-fuentes-y-procesamiento-de-geodatos.md) | Fuentes y procesamiento de geodatos | Aceptado |
| [0009](0009-construccion-de-consultas.md) | Construcción de consultas a los proveedores de noticias | Aceptado |
| [0010](0010-httpx2-para-llamadas-externas.md) | httpx2 para las llamadas HTTP externas y sus pruebas | Aceptado |
| [0011](0011-google-news-rss-fuera-de-produccion.md) | Google News RSS fuera de producción por sus términos de uso | Sustituido por el 0021 |
| [0012](0012-gdelt-desactivado-por-limite.md) | GDELT desactivado mientras responda 429 de forma persistente | Aceptado |
| [0013](0013-ingesta-periodica-e-indice-local.md) | Ingesta periódica e índice local de notas (GDELT por archivos y RSS de medios) | Aceptado (modificado por 0014) |
| [0014](0014-ngramas-de-gdelt.md) | Ngramas de GDELT como fuente del índice local | Aceptado |
| [0015](0015-extraccion-y-costo-de-ia.md) | Extracción de texto, su retención y el control de costo de la IA | Aceptado |
| [0016](0016-openai-como-ia.md) | OpenAI como IA del enriquecimiento, elegible junto a Gemini | Aceptado |
| [0017](0017-tierra-realista-y-fondo-espacial.md) | Tierra realista (texturas NASA), fondo espacial con three.js y movimiento del globo | Aceptado |
| [0018](0018-reportes-pdf-y-datos.md) | Reportes en PDF con mapa dibujado en el servidor y datos en CSV y GeoJSON | Aceptado |
| [0019](0019-paginas-de-searchapi.md) | Hasta 3 páginas de SearchApi por consulta, solo mientras vengan llenas | Aceptado |
| [0020](0020-colonias-de-openstreetmap.md) | Colonias de OpenStreetMap y reglas nuevas del geolocalizador | Aceptado |
| [0021](0021-google-news-rss-en-produccion.md) | Google News RSS en producción por dictamen de la Dirección (sustituye al 0011) | Aceptado |
| [0022](0022-programador-de-corridas-automaticas.md) | Las corridas automáticas FGR se programan en el reloj de Celery que ya existe | Aceptado |
| [0023](0023-perfiles-de-fuentes-y-browserwork.md) | Perfiles de fuentes (automático fijo y manual con switches) y conexión con BrowserWork | Aceptado |
| [0101](0101-entidades-independientes-de-la-fuente.md) | Entidades independientes de la fuente y `external_links` reservada (Fase 9) | Aceptado |
| [0102](0102-motor-visual-del-muro.md) | Motor visual del muro: capa propia de MapLibre sobre el mismo globo (bloque 0101–0105 de las fases 9–11) | Aceptado |
| [0103](0103-extraccion-de-entidades.md) | Las entidades se extraen solo de las notas que entran a un caso, en una llamada aparte (Fase 9.4) | Aceptado |
| [0104](0104-confirmacion-humana-obligatoria.md) | Confirmación humana obligatoria: todo nace sugerido y nada se fusiona solo (Fase 9) | Aceptado |
| [0105](0105-estatus-legal-y-procedencia.md) | Estatus legal y procedencia como campos de primera clase; "culpable" no existe (Fase 9) | Aceptado |
| [0106](0106-vinculos-y-fusiones-calculados-al-leer.md) | Vínculos y sugerencias de fusión calculados al leer; unir solo escribe `merged_into` (Fase 9.5) | Aceptado |
