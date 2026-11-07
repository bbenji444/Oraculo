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
| [0024](0024-reparacion-de-mojibake.md) | Reparación propia y conservadora del Mojibake, al entrar y en lo ya guardado | Aceptado |
| [0025](0025-duplicados-en-tres-niveles.md) | Duplicados en tres niveles: misma URL, misma nota con otro link y mismo hecho | Aceptado (nivel 3 en el 0026) |
| [0026](0026-historias-por-primera-nota.md) | Historias: el mismo hecho en varios medios se agrupa comparando con la primera nota | Aceptado |
| [0027](0027-fuentes-por-busqueda.md) | Cada búsqueda manual elige sus fuentes con switches y las guarda | Aceptado |
| [0028](0028-browserwork-como-fuente.md) | BrowserWork como fuente de la búsqueda manual (Bing y Google 2) | Aceptado (switches ocultos) |
| [0029](0029-categorias-de-noticias.md) | Categoría de cada noticia (el delito), en un catálogo en la base y con una llamada aparte de la IA | Aceptado |
| [0030](0030-relevancia-fgr-federal.md) | Relevancia FGR federal: la IA dice quién actúa y el concepto FGR lleva su regla | Aceptado |
| [0031](0031-corridas-automaticas-fgr.md) | Corridas automáticas del monitor FGR: una búsqueda nacional a las 07:00, 15:00 y 23:00 con fuentes gratis | Aceptado |
| [0032](0032-linea-del-tiempo.md) | Línea del tiempo: barras por fecha de publicación, orden por fecha del hecho | Aceptado |
| [0033](0033-reporte-oraculo.md) | Reporte PDF con el lenguaje visual de Oráculo: expediente, categorías, línea del tiempo y Estado ▸ Categoría ▸ Noticias | Aceptado |
| [0034](0034-auditoria-de-corridas.md) | Correcciones de la auditoría de las corridas FGR: Google News sin caché y partido, FGR con acentos, novedades en el PDF | Aceptado |
| [0035](0035-gods-eye-view-modulo-aparte.md) | God's Eye View como módulo aparte, tal cual, para evaluarlo (pestaña «God's Eye») | Retirado (27/10/2026) |
| [0036](0036-sistema-visual-consola-tactica.md) | Sistema visual «consola táctica»: paneles, botones y textos con animación al pasar el mouse | Aceptado |
| [0037](0037-diseno-centro-de-mando.md) | Diseño «Centro de mando», el principal: la búsqueda como una orden en una consola de misión, radar sobre el globo y expediente a la derecha (el de columna sigue con `?clasico`) | Aceptado |
| [0038](0038-subdivisiones-y-temas-generales.md) | Subdivisiones editables y temas generales: «FGR · Homicidio» exige las dos palabras | Aceptado |
| [0039](0039-envios-auditables.md) | Sección «Envíos»: reportes por correo vía Composio, con guía e intentos auditables | Aceptado (reglas reemplazadas por la 0040) |
| [0040](0040-horario-unico-de-corridas.md) | Horario único de las corridas, editable por el administrador: cada hora es un reporte nuevo desde la anterior y va a todos | Aceptado |
| [0101](0101-entidades-independientes-de-la-fuente.md) | Entidades independientes de la fuente y `external_links` reservada (Fase 9) | Aceptado |
| [0102](0102-motor-visual-del-muro.md) | Motor visual del muro: capa propia de MapLibre sobre el mismo globo (bloque 0101–0105 de las fases 9–11) | Aceptado |
| [0103](0103-extraccion-de-entidades.md) | Las entidades se extraen solo de las notas que entran a un caso, en una llamada aparte (Fase 9.4) | Aceptado |
| [0104](0104-confirmacion-humana-obligatoria.md) | Confirmación humana obligatoria: todo nace sugerido y nada se fusiona solo (Fase 9) | Aceptado |
| [0105](0105-estatus-legal-y-procedencia.md) | Estatus legal y procedencia como campos de primera clase; "culpable" no existe (Fase 9) | Aceptado |
| [0106](0106-vinculos-y-fusiones-calculados-al-leer.md) | Vínculos y sugerencias de fusión calculados al leer; unir solo escribe `merged_into` (Fase 9.5) | Aceptado |
