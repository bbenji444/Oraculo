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
| [0011](0011-google-news-rss-fuera-de-produccion.md) | Google News RSS fuera de producción por sus términos de uso | Aceptado (revisión legal pendiente) |
| [0012](0012-gdelt-desactivado-por-limite.md) | GDELT desactivado mientras responda 429 de forma persistente | Aceptado |
| [0013](0013-ingesta-periodica-e-indice-local.md) | Ingesta periódica e índice local de notas (GDELT por archivos y RSS de medios) | Aceptado (modificado por 0014) |
| [0014](0014-ngramas-de-gdelt.md) | Ngramas de GDELT como fuente del índice local | Aceptado |
| [0015](0015-extraccion-y-costo-de-ia.md) | Extracción de texto, su retención y el control de costo de la IA | Aceptado |
| [0016](0016-openai-como-ia.md) | OpenAI como IA del enriquecimiento, elegible junto a Gemini | Aceptado |
| [0017](0017-tierra-realista-y-fondo-espacial.md) | Tierra realista (texturas NASA), fondo espacial con three.js y movimiento del globo | Aceptado |
