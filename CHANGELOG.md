# Historial de cambios

Todos los cambios importantes de este proyecto se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [versionado semántico](https://semver.org/lang/es/): cada fase N cierra con la versión `v0.N.0`.

## [Sin publicar]

### Cambiado

- Explorar ya no muestra las gráficas "Top 5 estados con más noticias" ni "Tipos de noticias" (decisión de Benji: no aportaban y estorbaban). La derecha queda libre para el globo; el reporte en PDF conserva su página de análisis.
- Los créditos del mapa (INEGI, Natural Earth, NASA, OpenStreetMap) empiezan plegados en Explorar: solo se ve el botón "i" y aparecen al hacer clic. Antes MapLibre los dejaba abiertos porque el giro del globo no cuenta como arrastre.

## [0.7.0] - 2026-10-19

### Agregado

- **Fase 7 — Reportes** (§15, ADR-0018):
  - `POST /searches/{id}/report?format=pdf|html`: reporte A4 con portada (cifras clave, resumen ejecutivo con IA y datos clave calculados), página de análisis (mapa estático, tabla por subregión con barras, notas por día y medios con más notas), noticias agrupadas en dentro, fuera y sin ubicación, y anexo de metodología y fuentes. Nunca el texto de las notas.
  - Mapa estático en SVG dibujado con PostGIS: subregiones coloreadas por número de notas, vecinas recortadas al marco y anillo punteado para lo poco preciso.
  - Resumen ejecutivo con la IA (`summary_v1.md`) a partir de los resúmenes de las notas, guardado en la tabla nueva `reports` para no volver a pagarlo (~0.0003 USD medido).
  - `GET /searches/{id}/export?format=csv|geojson`: las notas en CSV (UTF-8 con BOM, sin fórmulas de Excel) y GeoJSON.
  - Cada reporte o exportación queda en la bitácora como `report.generated`; una búsqueda que corre responde `409 search_not_finished`.
  - Panel de Descargas activo en Explorar: Reporte (PDF), Datos (CSV), Mapa de puntos (GeoJSON) e Imprimir.
  - `/aggregates` acepta `level=locality`.
  - WeasyPrint 70, Jinja2 y Noto Sans incluida (OFL) para que la Ñ y los acentos salgan iguales en cualquier servidor; el instalador de WSL agrega Pango y HarfBuzz.

## [0.6.0] - 2026-10-17

### Agregado

- **Fase 6 — Frontend: globo y búsqueda** (§14, ADR-0017):
  - Pantalla **Explorar** (inicial): el globo domina la pantalla, con la Tierra de la NASA (de noche con las luces de las ciudades o de día) sobre un fondo de Vía Láctea y estrellas que titilan (three.js), y paneles translúcidos a los lados.
  - `make geo-earth`: descarga Blue Marble, Black Marble 2016 y Deep Star Maps con manifiesto y SHA-256, mezcla la noche con GDAL y genera teselas locales `earth_day.pmtiles` y `earth_night.pmtiles` (zoom 0–6). Al acercarse se funden con el mapa vectorial y las capas de INEGI.
  - Movimiento en un solo módulo (`map/motion.ts`): entrada hacia México, giro que se frena al acercarse y se reanuda tras 25 s sin uso, y vuelos cuya duración depende de la distancia y del zoom (1.2 a 4.5 s), con inclinación según el nivel. Hay control de velocidad (lenta, normal, rápida o sin animación) y se respeta "menos movimiento" del sistema.
  - Panel de búsqueda (§14.3): buscador de regiones, migas de pan, filtros Estado → Municipio → Localidad sincronizados con el globo, conceptos, fechas, estimación de consultas, créditos y costo de IA antes de buscar, y avance por etapas.
  - Resultados sobre el globo: mapa de calor, grupos de puntos, puntos que aparecen en cascada y laten al elegirlos, y anillo punteado para lo ubicado solo por estado o país. Un clic vuela a la nota y abre su ficha (§14.4) con línea guía.
  - Lista de noticias (Dentro, Fuera, Sin ubicación) con el interruptor "No relevantes", que vale para la lista y el globo a la vez; gráficas "Top 5 estados" y "Tipos de noticias", y panel de Descargas (sus botones funcionan en la Fase 7).
  - Pestaña **Historial**: reabre una búsqueda anterior en el globo sin gastar créditos.
  - Estado global con Zustand y servicios y hooks de búsquedas con TanStack Query (consulta el avance cada 2 s).
  - Prueba de humo del flujo principal (H1) con Testing Library y respuestas reales grabadas.

### Eliminado

- Pestaña temporal **Notas**, rutas `/api/v1/local-index/search` y `/stats`, y el globo viejo de **Geodatos**: los reemplaza la pantalla Explorar (Fase 6). El índice local sigue buscando como proveedor dentro de cada búsqueda.

## [0.5.0] - 2026-10-17

### Agregado

- **Fase 5 — API de búsqueda y resultados** (`docs/api.md`, con ejemplos de `curl` reales):
  - `POST /searches/estimate`: consultas, créditos del mes y costo máximo de la IA, sin gastar.
  - `POST /searches`: crea la búsqueda y la manda al worker (`202`). Antes revisa la llave de la IA (`503`), el tope mensual (`409`) y el máximo de consultas.
  - `GET /searches/{id}` (estado, avance y costo) y `GET /searches` (historial con cursor).
  - `GET /searches/{id}/articles`: notas con resumen, conceptos, ubicación y punto. Filtros `relevant`, `in_region`, `precision` y `concept_id`, con cursor por fecha.
  - `GET /searches/{id}/aggregates`: mapa de calor por estado, municipio o país, sin repartir lo menos preciso.
  - `GET /articles/{id}`: todas sus menciones de lugar (nunca el texto completo).
  - Errores 500 y 503 con el formato uniforme y OpenAPI revisado: cada ruta documenta solo sus errores y cada grupo tiene descripción.
  - `PlanSearch`: la API y `make buscar` estiman igual.

### Corregido

- Borrar un concepto que ya se usó en una búsqueda ahora lo desactiva (borrado lógico, §13). Antes `is_used_in_searches` siempre respondía "no" y el borrado físico chocaba con `search_concepts` (error 500).

## [0.4.0] - 2026-10-17

### Agregado

- **Fase 4 — Pipeline, IA y geolocalización.**
  - Tablas de búsquedas y notas (migraciones 0011 a 0013):
    - `searches` y `search_concepts` (los conceptos se copian al buscar);
    - `articles` (una por URL canónica) y `article_texts` (solo para procesar, se borra a los 30 días);
    - `article_concepts`, `article_locations` (el punto sale del catálogo, nunca de la IA) y `search_results`;
    - `processing_errors`.
  - Duplicados: URL canónica sin rastreo, `www.` ni AMP, y títulos casi iguales (≥ 0.9 con rapidfuzz, ±1 día).
  - Extracción del texto con trafilatura. Si falla, se usa título + fragmento (`fallback`).
  - IA detrás de `LLMPort`, con prompt versionado (`enrich_v1`) y respuesta validada con un reintento:
    - OpenAI (`gpt-6-luna`, por defecto; ADR-0016) o Gemini (`gemini-2.5-flash`), elegible con `LLM_PROVIDER`;
    - costo estimado antes de gastar, tope de 150 notas por búsqueda y tokens y costo registrados (ADR-0015).
  - Geolocalizador de §11:
    - alias (`geodata/aliases.csv`) y desempate por los estados de la nota y la región buscada;
    - si sigue ambiguo, sube al estado o queda sin ubicar;
    - parecidos por trigramas con confianza reducida.
  - `RunSearch`: las 8 etapas de §9 con avance real en `searches.progress`.
    - Un error en una nota no detiene la búsqueda. Si falla más de la mitad, queda `partial`.
    - Las notas ya enriquecidas se reutilizan sin pagar.
  - Tarea de Celery `search.run`. La limpieza diaria también borra los textos vencidos.
  - `make buscar`: muestra créditos y costo máximo, pide "si", corre la búsqueda (en el worker o con `--aqui`) y enseña 5 notas con lugar, precisión y confianza.
  - `make reubicar`: vuelve a ubicar las notas de una búsqueda con las reglas y el catálogo vigentes sin pagar a la IA; con `--con-ia` las vuelve a pasar por la IA desde su texto guardado (0 créditos). Las pistas de lugar de la IA se guardan (migración 0014).
  - Globo con rotación automática e inclinación de 15°.

### Corregido

- Geolocalización, con lo aprendido en la primera búsqueda real (Extorsión en Jalisco: 18 notas, 1 crédito y 0.0068 USD):
  - alias de los municipios cuyo nombre oficial es más largo que el de uso diario ("Heroica Ciudad de Juchitán de Zaragoza", "Santo Domingo Tehuantepec"…);
  - una localidad de otro estado ya no se usa si la nota nombra sus estados (la "colonia La Gloria" de Juchitán caía en Guanajuato).

## [0.3.0] - 2026-10-16

### Agregado

- **Fase 3 — Proveedores e ingesta.**
  - Cliente HTTP compartido (httpx2, ADR-0010) con:
    - tiempo máximo por petición;
    - reintentos con espera creciente solo ante 429, 5xx o red caída;
    - espera mínima tras un 429 y User-Agent propio;
    - registro de cada intento fallido.
  - Adaptadores con el mismo contrato (`NewsProviderPort`) y notas en un formato común (`RawArticle`):
    - SearchApi (Google News, la llave viaja en el encabezado);
    - GDELT DOC;
    - Google News RSS.
  - `ExecuteQueries` aplica, en este orden:
    - el presupuesto de 10 consultas por búsqueda;
    - la caché de consultas idénticas (Redis, 6 h);
    - el tope mensual de créditos de SearchApi (100, por mes de la Ciudad de México);
    - el registro de cada petición en `provider_queries` (migración 0007).
  - `make probar-proveedor` (una consulta real con confirmación y fixture sin la llave) y `make gdelt-diagnostico` (reintento diario de D1, ADR-0012).
  - **Índice local de notas** (ADR-0013):
    - tablas `news_index` e `ingest_runs` (migraciones 0008 y 0009);
    - lectura de los archivos GKG de GDELT (solo notas en español con México, verificadas con MD5) y de RSS de medios desde `fuentes/medios_rss.csv`;
    - equivalencias de estados FIPS→INEGI (`geodata/fips_inegi.csv`).
  - Ingesta automática cada 15 minutos con el reloj de Celery (`celery beat`), que arranca `make up`, más limpieza diaria por retención (90 días). `make ingesta` corre una vez y muestra 5 ejemplos.
  - Proveedor `indice_local`:
    - palabra clave completa (sin acentos, con Ñ), exclusiones y lugar en el texto, o la pista de GDELT si la región es un estado;
    - días en hora de la Ciudad de México;
    - gratis y sin caché.
  - `make ingesta-historial DIAS=N`: vista previa del tamaño sin descargar y 5 ejemplos reales; solo baja todo con `DESCARGAR=si`.
  - **Ngramas de GDELT** (ADR-0014): notas en español que mencionan México, con frases del texto completo (`body_terms`, migración 0010) solo para buscar y conservadas 30 días. `indice_local` busca también en el cuerpo. `make ngramas-muestra` prueba una hora real.
  - Pestaña **Notas** (vista temporal hasta F6) y endpoints temporales `/api/v1/local-index/search` y `/stats`.
  - Primera consulta real a SearchApi (1 crédito): 10 notas normalizadas; confirma `iso_date`, `link=resolved` y `time_period`. También quedó grabada la primera respuesta de GDELT DOC con notas.
  - Globo: gira solo (una vuelta cada 90 s, se detiene al tocarlo) con el eje inclinado 15°, como un globo de escritorio. Se endereza al acercarse a una región.
  - ADR-0010 a ADR-0014.

### Cambiado

- Especificación v1.8: F3 pasa a ser "Proveedores e ingesta".
- `PlannedQuery` lleva exclusiones y lugar por separado, y `PlaceFacts`/`QueryPlace` la clave INEGI del estado.
- "Probar concepto" muestra también la consulta del índice local, escrita en palabras.
- El worker y el reloj de Celery escriben logs JSON, igual que la API.
- Especificación v1.9: los ngramas de GDELT son la fuente principal del índice local y el GKG (solo títulos) queda apagado por defecto (ADR-0014).
- RSS de medios: La Jornada, El Universal e Infobae México **encendidos** por decisión de Benji (`MEDIA_RSS_ENABLED=true`); cada medio se apaga en `fuentes/medios_rss.csv`.

### Corregido

- GDELT repetía la misma ubicación por cada mención; ahora se guarda una vez.
- El índice local ya no acepta notas solo porque GDELT las ubicó en el estado buscado: en datos reales metía notas de otros estados (ADR-0014).
- El tamaño y el MD5 de los archivos de GDELT se leen de `x-goog-hash` y `x-goog-stored-content-length`: Google quita el ETag cuando recomprime al vuelo.

### Desactivado

- Google News RSS fuera de producción por sus términos de uso (ADR-0011, `NEWS_RSS_ENABLED=false`).
- API DOC de GDELT apagada mientras responda 429 (ADR-0012, `GDELT_ENABLED=false`); sus archivos sí se usan en el índice local.

## [0.2.0] - 2026-10-16

### Agregado

- **Fase 2 — Conceptos.**
  - Tabla `concepts` (migración 0005) con nombre único sin importar mayúsculas ni acentos, borrado lógico y validaciones:
    - al menos una palabra clave;
    - sin palabras repetidas;
    - ninguna exclusión igual a una palabra clave;
    - sin caracteres que los buscadores toman como órdenes;
    - color `#RRGGBB`.
  - Bitácora de auditoría `audit_log` (migración 0006): cada alta, edición y borrado de un concepto queda con usuario, IP, antes y después, en la misma transacción que el cambio.
  - Constructor de consultas `build_queries` con un dialecto por proveedor (SearchApi, Google News RSS y GDELT), probado con los casos de §7.2:
    - términos de búsqueda curados por lugar (`geodata/search_terms.csv`, migración 0004);
    - el estado cuando un municipio tiene nombre repetido;
    - filtros por país con ISO-2 y FIPS de Natural Earth.
  - Endpoints `/api/v1/concepts`: listar por cursor, detalle, crear, editar, borrar y "Probar concepto" para un concepto guardado o para un borrador sin guardar.
  - `make seed` con los 5 conceptos semilla y `make geo-terms` para aplicar términos de búsqueda y códigos de país sin recargar el catálogo.
  - Pantalla **Conceptos**: tabla con interruptor de activo, formulario con palabras como "chips" y errores por campo, y "Probar concepto" con las consultas exactas por proveedor.
  - ADR-0009 (construcción de consultas).

### Cambiado

- Especificación v1.4: `search_terms` y códigos de país en `regions`, exclusiones también en GDELT, `name_norm` y `deleted_at` en `concepts`, `POST /concepts/preview`.
- Frontend: cliente HTTP compartido (`services/http.ts`) con soporte de POST, PATCH, DELETE y detalles de error.

### Corregido

- `Makefile`: un `\n` literal en la lista `.PHONY`.

### Pendiente

- `is_used_in_searches` responde "no" hasta que F4 cree `search_concepts`; hasta entonces borrar un concepto siempre es físico.
- Límites de largo y operadores no documentados de los proveedores (`when:`, varios bloques OR en GDELT), marcados `VERIFICAR` para F3.

## [0.1.0] - 2026-10-16

### Agregado

- **Fase 1 — Geodatos.**
  - Tabla `regions` (migraciones 0002 y 0003) con 258 países, 32 estados, 2,478 municipios y 296,850 localidades de INEGI (Marco Geoestadístico, Encuesta Intercensal 2025) y Natural Earth.
  - Pipeline `make geo-download`, `geo-inspect`, `geo-load`, `geo-validate`, `geo-tiles` y `geo-basemap`:
    - descarga por HTTP Range solo del marco integrado de INEGI, con manifiesto y SHA-256;
    - detección de encoding con los bytes crudos;
    - carga idempotente con reparación de geometrías;
    - los 11 criterios de aceptación de §12;
    - PMTiles por capa y mapa base de Protomaps autoalojado (mundo z6, México z14).
  - Normalización de nombres que conserva la Ñ, compartida por el cargador y el buscador.
  - Endpoints `/api/v1/regions`: listas por nivel, detalle con migas de pan, hijas, búsqueda por nombre o alias y región en un punto. Paginación por cursor y formato uniforme de errores en español.
  - Explorador de geodatos: globo 3D con MapLibre v6, buscador con autocompletado, tooltip, tarjeta con migas de pan y vuelo a la región.
  - `make db-shell`, `make db-dump` y guía para consultar y migrar la base (`docs/base-de-datos.md`).
  - ADR-0007 (MapLibre v6) y ADR-0008 (fuentes y procesamiento de geodatos).

### Cambiado

- Especificación v1.3: MapLibre GL JS v6 y lógica del pipeline en `backend/app/geodata/`.
- nginx: tipos correctos para sprite, fuentes y el worker `.mjs` de MapLibre; `index.html` sin caché; la CSP ya no permite `blob:` en `worker-src`.

### Corregido

- GDAL ya no lee directamente de `/mnt/d`, donde recibió bytes dañados en WSL. Ahora se extrae con verificación de CRC al disco de Linux.

## [0.0.0] - 2026-10-15

### Agregado

- **Fase 0 — Cimientos.**
  - Entorno de desarrollo sin Docker, con los servicios nativos en Ubuntu dentro de WSL (ADR-0006). `make bootstrap` instala PostgreSQL 16 + PostGIS 3.6, Redis 8, nginx, uv y Python 3.12 con un script que se puede repetir.
  - Comandos `make up`, `down`, `status`, `logs`, `test`, `lint`, `format`, `migrate` y `frontend-build`.
  - Endpoint `GET /api/v1/health` con el estado de la API, la base de datos (versión y extensiones), Redis y el worker. Responde 200 si todo está bien y 503 si algo falla, con el detalle en español.
  - Página inicial "Estado del sistema" con semáforo por componente, actualizada cada 10 segundos.
  - Backend FastAPI con arquitectura hexagonal, configuración por variables de entorno, logs JSON, Alembic (migración inicial de extensiones) y worker Celery.
  - Frontend React 18 + TypeScript + Vite + Tailwind CSS v4, con ESLint, Prettier y Vitest.
  - nginx como punto de entrada único (<http://localhost:8080>): frontend, proxy a la API, teselas con Range y encabezados de seguridad.
  - `.gitattributes` que fuerza finales de línea LF (CRLF solo en scripts de Windows), `.editorconfig` y pre-commit.
  - ADRs 0001 a 0006, README de arranque desde cero y documentación de arquitectura.

### Cambiado

- Especificación v1.2: campo `aliases` en `regions`, filtro `sourcecountry` en GDELT, nota sobre los links de Google News RSS y entorno de desarrollo sin Docker.
