# Especificación — Monitor de Noticias Geolocalizadas

Versión 2.10 · Octubre 2026 · Responsable: Benji

Este documento define **qué** se construye. Las reglas de **cómo** se trabaja están en `CLAUDE.md`.
Cuando algo no esté claro aquí, pregunta antes de suponer.

---

## 1. Visión

Un analista abre el sistema y ve un globo terráqueo 3D que puede rotar.
Hace zoom a México, da click en un estado, luego en un municipio o alcaldía, elige uno o varios **conceptos** (por ejemplo "Ciberseguridad" o "Secuestro") y un rango de fechas, y presiona **Buscar**.

El sistema entonces:

1. consulta varias fuentes de noticias,
2. elimina duplicados,
3. lee cada nota,
4. decide si de verdad trata del concepto,
5. la resume,
6. detecta **dónde ocurrió** el hecho,
7. la pinta en el globo,
8. permite generar un reporte en PDF.

Los conceptos no están fijos en el código. El usuario los crea, edita, desactiva o elimina desde una sección de administración, y cada concepto funciona como una **plantilla de búsqueda** reutilizable.

---

## 2. Glosario

| Término | Significado |
|---|---|
| **Concepto** | Tema de búsqueda definido por el usuario: nombre, descripción, palabras clave, términos de exclusión y color. Ejemplo: "Ciberseguridad". |
| **Región** | Unidad geográfica seleccionable. Niveles: `country` (país), `state` (estado), `municipality` (municipio o alcaldía), `locality` (localidad). |
| **Búsqueda** | Ejecución concreta: conceptos + región + rango de fechas. Tiene estado, progreso y créditos consumidos. |
| **Consulta** | Petición individual a un proveedor de noticias, generada a partir de una búsqueda. |
| **Proveedor** | Fuente externa de noticias: SearchApi (Google News), GDELT, Google News RSS. |
| **Noticia** | Artículo normalizado y deduplicado. Una misma noticia puede aparecer en muchas búsquedas. |
| **Mención geográfica** | Lugar que aparece en el texto de la noticia, extraído por el LLM y resuelto contra el catálogo INEGI. |
| **Precisión** | Nivel más específico al que se pudo ubicar la noticia: `locality`, `municipality`, `state`, `country` o `unknown`. |
| **En región** | La ubicación principal de la noticia cae dentro de la región buscada (o en una región hija). |

---

## 3. Historias de uso (narrativas reales)

### H1 — Búsqueda puntual

> Benji entra en la mañana. El globo gira despacio. Lo detiene, hace zoom sobre México y da click en la Ciudad de México: la cámara vuela al estado, se resalta y aparecen las 16 alcaldías. Da click en Iztapalapa. En el panel, la región dice "México › Ciudad de México › Iztapalapa".
>
> Selecciona el concepto "Ciberseguridad" y el rango "Últimos 7 días". Antes de buscar, el sistema le avisa: "Se harán 3 consultas (aprox. 1 crédito de SearchApi)". Presiona Buscar.
>
> Una barra muestra las etapas: consultando fuentes → leyendo notas → analizando → ubicando. Al terminar aparecen 9 noticias. 6 están marcadas en Iztapalapa. 2 se ubican solo a nivel "Ciudad de México" y se dibujan con otro estilo en el centro del estado. 1 resultó ser de otro estado y aparece en la lista como "fuera de la región".
>
> Da click en una noticia: la cámara vuela al punto y se abre la tarjeta con título, medio, fecha, resumen, concepto, ubicación con su precisión y el link a la nota original.

### H2 — Administración de conceptos

> En la sección "Conceptos", Benji crea "Extorsión telefónica":
> - palabras clave: `extorsión telefónica`, `llamada de extorsión`, `montadeudas`, `secuestro virtual`;
> - exclusión: `simulacro`.
>
> Presiona "Probar concepto" y ve las consultas exactas que se generarían para "Jalisco", sin gastar créditos. Guarda. Desde ese momento el concepto aparece en el panel de búsqueda.
>
> Una semana después desactiva el concepto "Prueba" sin borrarlo. Las búsquedas viejas que lo usaron siguen mostrando su nombre.

### H3 — Panorama nacional

> Benji selecciona solo "México" (país), el concepto "Secuestro" y "Últimos 30 días". El globo pinta los estados en un mapa de calor según la cantidad de noticias. Hace zoom en Guerrero y el mapa de calor cambia a nivel municipio.

### H4 — Fuera de México

> El globo permite seleccionar otros países a nivel país. Benji da click en Colombia y busca "Ciberseguridad". La búsqueda funciona igual, pero sin división interna: el detalle estatal y municipal existe solo para México en esta versión.

### H5 — Reporte

> Con los resultados de H1 en pantalla, Benji presiona "Generar reporte". Obtiene un PDF con:
> - portada (concepto, región, rango, fecha de generación, usuario),
> - resumen ejecutivo generado,
> - conteo por alcaldía,
> - mapa estático,
> - lista de noticias con resumen, fuente, fecha y link.

---

## 4. Alcance

### Incluido en esta versión

- Globo 3D rotable con países clickeables; México con estados, municipios/alcaldías y localidades.
- Selección de región desde el mapa **y** desde filtros encadenados (Estado → Municipio → Localidad) con buscador por nombre. Mapa y filtros siempre sincronizados.
- CRUD de conceptos desde la UI.
- Búsqueda asíncrona en tres proveedores, con estimación previa de consultas y créditos.
- Deduplicación, extracción de texto, clasificación de relevancia, resumen y geolocalización con LLM.
- Visualización: mapa de calor por región, marcadores agrupados, lista de resultados y tarjeta de detalle.
- Historial de búsquedas.
- Reporte en HTML y PDF.
- Bitácora de auditoría.
- API REST documentada (OpenAPI) para integrarse después al sistema principal.

### Fuera de alcance (por ahora; la arquitectura no debe impedirlo)

- Monitoreo programado (búsquedas recurrentes automáticas con alertas). Se planea para la Fase 8.
- Colonias y códigos postales como polígonos.
- División interna de países distintos a México.
- Integración con WhatsApp y n8n (solo se deja la API lista).
- Extracción de personas mencionadas en las notas.

---

## 5. Arquitectura

### 5.1 Vista general

```
┌────────────────────────── Navegador ──────────────────────────┐
│  React + TypeScript + MapLibre GL (proyección globo)          │
│  Panel búsqueda · Globo · Resultados · Conceptos · Historial  │
└───────────────┬──────────────────────────────┬────────────────┘
                │ /api/v1 (JSON)               │ /tiles/*.pmtiles (HTTP Range)
┌───────────────▼──────────────┐   ┌───────────▼────────────────┐
│ nginx (sirve frontend,       │   │ Archivos PMTiles           │
│ tiles y proxy a la API)      │   │ (mapa base + INEGI)        │
└───────────────┬──────────────┘   └────────────────────────────┘
┌───────────────▼──────────────┐
│ API FastAPI                  │── encola ──┐
│ (routers delgados)           │            │
└───────────────┬──────────────┘   ┌────────▼───────────────────┐
                │                  │ Redis (cola + caché)       │
                │                  └────────┬───────────────────┘
                │                  ┌────────▼───────────────────┐
                │                  │ Worker Celery: pipeline    │
                │                  │ consultas → dedupe →       │
                │                  │ extracción → LLM → geo     │
                │                  └──┬──────────┬──────────┬───┘
┌───────────────▼──────────────────────▼───┐   ┌──▼──────┐ ┌─▼──────────┐
│ PostgreSQL 16 + PostGIS + pg_trgm +      │   │SearchApi│ │ Gemini API │
│ unaccent                                 │   │GDELT    │ └────────────┘
└──────────────────────────────────────────┘   │News RSS │
                                               └─────────┘
```

### 5.2 Capas del backend (arquitectura hexagonal)

| Capa | Responsabilidad | Puede depender de |
|---|---|---|
| `domain/` | Entidades y reglas puras (Concept, Region, Article, GeoMention, Precision). Sin frameworks. | Nada |
| `application/` | Casos de uso (buscar noticias, gestionar conceptos, generar reporte) y **puertos** (interfaces). | `domain` |
| `adapters/` | Implementaciones de los puertos: proveedores, LLM, extractor, repositorios SQLAlchemy, generador de PDF, caché. | `application`, `domain` |
| `api/` | Routers FastAPI, esquemas de entrada y salida, autenticación. | `application` |
| `worker/` | Tareas Celery que invocan casos de uso. | `application` |

**Por qué hexagonal:** los proveedores de noticias y los LLM cambian de precio, de API o desaparecen; la API de Google es justo un ejemplo. Con puertos y adaptadores, cambiar de proveedor significa escribir un adaptador nuevo sin tocar la lógica de negocio. Eso es lo que permite escalar.

**Puertos principales:**

```python
class NewsProviderPort(Protocol):
    name: str
    async def search(self, query: PlannedQuery) -> list[RawArticle]: ...
    def estimate_cost(self, query: PlannedQuery) -> Decimal: ...

class LLMPort(Protocol):
    async def enrich(self, article: ArticleText, concepts: list[Concept]) -> Enrichment: ...

class ArticleExtractorPort(Protocol):
    async def extract(self, url: str) -> ExtractedText | None: ...

class GeoResolverPort(Protocol):
    def resolve(self, mention: GeoMention, context: GeoContext) -> ResolvedLocation: ...
```

### 5.3 Estructura del repositorio

```
monitor-noticias/
├── CLAUDE.md
├── README.md
├── CHANGELOG.md
├── Makefile
├── .env.example
├── scripts/
│   └── dev/                 # instalación y arranque de servicios en WSL (ver ADR-0006)
├── docs/
│   ├── ESPECIFICACION.md
│   ├── arquitectura.md
│   ├── api.md
│   └── adr/
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/            # config, logging, errores base
│   │   ├── domain/
│   │   ├── application/
│   │   │   ├── ports/
│   │   │   └── use_cases/
│   │   ├── adapters/
│   │   │   ├── providers/   # searchapi.py, gdelt.py, google_news_rss.py
│   │   │   ├── llm/         # gemini.py + prompts/ versionados
│   │   │   ├── extraction/
│   │   │   ├── persistence/
│   │   │   ├── geo/
│   │   │   ├── cache/
│   │   │   └── reports/     # plantillas Jinja2 + WeasyPrint
│   │   ├── api/v1/
│   │   └── worker/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/        # respuestas grabadas de cada proveedor
├── frontend/
│   └── src/
│       ├── components/      # Globe/, SearchPanel/, Results/, Concepts/, History/
│       ├── services/        # cliente de la API
│       ├── stores/          # Zustand
│       ├── hooks/
│       └── styles/
├── geodata/
│   ├── README.md
│   ├── raw/                 # descargas originales (en .gitignore)
│   ├── scripts/             # mapa base y envoltorios; la lógica del pipeline vive en
│   │                        # backend/app/geodata/ (probada y tipada con el backend)
│   └── output/              # PMTiles generados (en .gitignore)
└── nginx/
```

### 5.4 Stack y justificación

| Pieza | Elección | Por qué |
|---|---|---|
| API | FastAPI + Pydantic v2 | Asíncrono (muchas llamadas HTTP externas), validación fuerte, OpenAPI automático para integrarse al sistema principal. |
| ORM y migraciones | SQLAlchemy 2 + Alembic + psycopg 3 | Estándar maduro; las migraciones versionadas dejan rastro de cada cambio de esquema. |
| Base de datos | PostgreSQL 16 + PostGIS + `pg_trgm` + `unaccent` | Consultas espaciales ("¿esta noticia cae en este municipio?") y búsqueda difusa de nombres. Es el motor que ya usa el proyecto. |
| Cola | Celery + Redis | Una búsqueda tarda decenas de segundos y no puede bloquear la API. Celery es el estándar más conocido; Redis sirve también de caché. |
| HTTP externo | httpx2 (async) + tenacity (ADR-0010) | Timeouts, reintentos con backoff y concurrencia controlada. httpx2 es la continuación mantenida de httpx; las pruebas usan su `MockTransport`. |
| Extracción de texto | trafilatura | Extrae el cuerpo del artículo sin menús ni anuncios. |
| LLM | Gemini 2.5 Flash vía SDK oficial vigente (`google-genai`; verificar), detrás de `LLMPort` | Ya se usa en el proyecto, es barato y rápido. El puerto permite cambiarlo. |
| Reportes | Jinja2 + WeasyPrint | Una misma plantilla HTML sirve para vista web y para PDF. |
| Frontend | React 18 + TypeScript + Vite | Ecosistema amplio, tipado. |
| Globo y mapa | MapLibre GL JS v6 (proyección `globe`; ver ADR-0007) | Globo 3D rotable que hace zoom continuo hasta nivel calle con la misma librería. Open source, sin llave ni costo. |
| Tierra y espacio | Texturas de la NASA en PMTiles raster y fondo de estrellas con three.js (ADR-0017) | Tierra realista de día y de noche, y un universo detrás del globo, sin depender de servidores de terceros. |
| Teselas | PMTiles autoalojados (mapa base Protomaps + capas INEGI) | No se depende de servidores de mapas externos, algo importante en un sistema institucional. Un solo archivo por capa, servido por nginx con HTTP Range. |
| Estado UI | Zustand + TanStack Query | Simple y predecible; caché de datos del servidor. |
| Estilos | Tailwind CSS | Rápido, consistente; modo oscuro sencillo. |

Cualquier cambio a esta tabla requiere un ADR.

---

## 6. Modelo de datos (PostgreSQL)

Todas las tablas tienen `created_at` y `updated_at` (`timestamptz`, UTC) salvo que se indique lo contrario.

**`regions`** — catálogo geográfico unificado
- `id` bigserial PK
- `level` enum(`country`, `state`, `municipality`, `locality`)
- `code` text único. Para México se usa la clave INEGI CVEGEO: estado `09`, municipio `09007`, localidad `090070001`. Para países, el ISO-A3 (`COL`).
- `parent_id` FK → regions
- `country_code` (`MEX`, `COL`...)
- `name` (original, con acentos) y `name_norm` (para comparar)
- `aliases` text[] (variantes como se escriben en medios: `CDMX`, `Neza`, `Edomex`) y `aliases_norm` text[] (las mismas, normalizadas como `name_norm`). Las usa el resolutor geográfico (sección 11).
- `search_terms` text[] (términos con que se busca el lugar en los proveedores; si está vacío se usa `name`). Los usa `build_queries` (sección 7.2, ADR-0009).
- `iso_a2` y `fips_code` (solo países): códigos que piden los proveedores para filtrar por país (ADR-0009).
- `display_prefix` (`Alcaldía`, `Municipio`, `Estado`...)
- `geom` geometry(MultiPolygon, 4326), nulo en localidades sin polígono
- `centroid` geometry(Point, 4326)
- `bbox`: rectángulo que contiene toda la región
- `focus_bbox`: rectángulo de su parte principal, sin islas ni territorios lejanos (Francia sin Guayana, Estados Unidos contiguo); `NULL` si es de una sola parte. Con él vuela la cámara y se encuadra el mapa del reporte
- `population` (si la fuente la trae)
- Índices: GIST(`geom`), GIST(`centroid`), GIN(`name_norm gin_trgm_ops`), GIN(`aliases_norm`), BTREE(`level`, `parent_id`), BTREE(`code text_pattern_ops`)

**Tabla `places`** (ADR-0020): colonias, zonas y parajes de OpenStreetMap que trae el mapa base, cada uno con `name`, `name_core` (normalizado sin palabra genérica, índice `text_pattern_ops`), `kind`, `point` y `municipality_id` (municipio de INEGI que lo contiene, con índice). Se llena con `make geo-places`. `article_locations` guarda además `place_name` (la colonia usada) y `municipality_hint` (el municipio que sugiere la IA).

**Truco clave:** la jerarquía INEGI está en el prefijo del código. "¿La noticia ubicada en `09007` está dentro de `09`?" se resuelve con `code LIKE '09%'`, sin geometría.

**`concepts`**
- `id`
- `name` y `name_norm` (único entre los no borrados, sin importar mayúsculas ni acentos)
- `description`
- `keywords` text[]
- `exclude_terms` text[]
- `color` (hex)
- `is_active`
- `created_by`
- `deleted_at` (borrado lógico)

**`searches`**
- `id` uuid
- `user_id`
- `region_id`
- `date_from`, `date_to`
- `status` enum(`pending`, `running`, `completed`, `partial`, `failed`)
- `progress` jsonb (etapa actual y conteos)
- `queries_planned`
- `credits_estimated`, `credits_used`
- `results_count`
- `error_summary`
- `started_at`, `finished_at`

**`search_concepts`**
- `search_id`, `concept_id`
- Copia del nombre y las palabras clave **al momento de buscar**, para que editar un concepto no altere el historial.

**`provider_queries`**
- `id`, `search_id` (opcional: las consultas del comando de prueba no pertenecen a una búsqueda; la llave foránea llega con `searches` en F4)
- `provider`
- `query_text`, `params` jsonb
- `status`, `http_status`
- `results_count`
- `from_cache`
- `cost_credits`
- `duration_ms`
- `error_message`

**`articles`** — global y deduplicado
- `id` bigserial
- `url_canonical` (único), `url_hash`
- `title`, `title_norm`
- `source_name`, `source_domain`
- `published_at`
- `snippet`
- `language`
- `extraction_status`
- `text_hash`
- `summary`
- `event_date`
- `enrichment_status`
- `llm_model`, `prompt_version`
- `first_seen_at`
- El texto extraído se usa para procesar y se guarda en una tabla aparte, `article_texts`, con política de retención configurable. No se expone en la API.

**`article_concepts`**
- `article_id`, `concept_id`
- `is_relevant`
- `relevance_score`
- `relevance_reason`

**`article_locations`**
- `id`, `article_id`
- `mention_text`
- `role` enum(`event`, `mentioned`)
- `region_id` (nulo si no se resolvió)
- `precision`
- `confidence`
- `is_primary`
- `point` geometry(Point, 4326)

**`search_results`**
- `search_id`, `article_id`
- `provider`
- `provider_rank`
- `in_region`

**`processing_errors`**
- `id`
- `search_id`, `article_id` (nulos según el caso)
- `stage`
- `error_type`
- `message`
- `payload` jsonb

**`audit_log`**
- `id`
- `user_id`
- `action` (por ejemplo `concept.created`)
- `entity_type`, `entity_id`
- `payload` jsonb (valores antes y después)
- `ip`
- `created_at`

**`reports`** (F7, ADR-0018) — el resumen ejecutivo de cada búsqueda, para no volver a pagarlo
- `id`
- `search_id` (único, con índice)
- `executive_summary`
- `llm_provider`, `llm_model`, `prompt_version`
- `llm_tokens_in`, `llm_tokens_out`, `llm_cost_usd`
- `created_by`, `created_at`

**`users`** — se crea en la Fase 8; antes, un usuario fijo de desarrollo.

**Tablero de investigación (Fase 9.2, migraciones 0018 y 0019)** — el detalle de columnas está en `docs/PLAN_FASES_9-10-11.md` §9.6 y en `docs/base-de-datos.md`. Cambios aprobados respecto del plan:
- `entities`, `entity_aliases`, `entity_mentions`, `relationships` y `external_links` (reservada y vacía, ADR-0101).
- Revisión en tres estados (`review_status`: `suggested`, `confirmed`, `discarded`, con `reviewed_by` y `reviewed_at`) en lugar de `is_confirmed` (ADR-0104).
- Estatus legal con códigos en inglés: `mentioned`, `alleged`, `detained`, `charged` (vinculado a proceso, agregado), `victim`, `witness`, `official`; nunca "culpable" (ADR-0105).
- Los lugares se ligan a `regions` o `places`; su punto sale del catálogo.
- `entity_mentions.evidence_span`: cita de máximo 300 caracteres, que sobrevive al borrado del texto (ADR-0015).
- `cases`, `case_members` (acceso por caso hasta la Fase 8), `case_articles` y `case_entities` con llaves foráneas reales en lugar de `case_items`, y `case_notes` con a lo más un ancla.

**Extracción de entidades (Fase 9.4, migración 0020, ADR-0103)**
- `entity_extractions`: lo que respondió la IA de cada nota (propuestas revisadas contra el texto y descartadas con su motivo), con modelo, origen del texto (`full_text` o `title_snippet`), tokens, costo y error. Única por (`article_id`, `prompt_version`): se reutiliza entre casos sin volver a pagar.
- `case_articles.entities_status` (`pending`, `queued`, `done`, `failed`, `skipped`) y `entities_cost_usd` (lo que pagó ese caso por la nota).
- `entity_mentions`: única por (`entity_id`, `article_id`, `evidence_span`).

---

## 7. Conceptos

### 7.1 Ejemplo

```json
{
  "name": "Ciberseguridad",
  "description": "Ataques informáticos, robo de datos y fraudes digitales",
  "keywords": ["ciberataque", "hackeo", "ransomware", "filtración de datos", "phishing"],
  "exclude_terms": ["curso", "webinar", "diplomado"],
  "color": "#2E86DE",
  "is_active": true
}
```

**Conceptos semilla** (`make seed`): Ciberseguridad, Secuestro, Extorsión, Robo de vehículos, Desaparición de personas. Las palabras clave de cada uno se proponen y Benji las valida.

### 7.2 Constructor de consultas (`build_queries`)

**Entrada:**
- Concepto "Ciberseguridad".
- Región: Iztapalapa (municipio, estado CDMX).
- Ventana: últimos 7 días.

**Salida esperada:**

| Proveedor | Consulta |
|---|---|
| SearchApi (`google_news`) | `(ciberataque OR hackeo OR ransomware OR "filtración de datos" OR phishing) Iztapalapa -curso -webinar -diplomado` · país MX · idioma español · filtro de tiempo "última semana" (verificar nombres exactos de parámetros en la documentación) |
| Google News RSS | La misma consulta + `when:7d` · `hl=es-419&gl=MX&ceid=MX:es-419` |
| GDELT DOC 2.0 | `(ciberataque OR hackeo OR ransomware OR "filtración de datos" OR phishing) Iztapalapa -curso -webinar -diplomado sourcelang:spanish sourcecountry:MX` · `timespan=7d` · `mode=ArtList` · `format=json` · `maxrecords=250` |

**Nota sobre GDELT:** `sourcelang:spanish` solo filtra por idioma, así que sin otro filtro entrarían medios de España, Argentina, etc. Por eso se agrega `sourcecountry:<país>`, que filtra por el país del medio. La documentación oficial confirma la sintaxis (nombre del país en inglés sin espacios, o código FIPS de 2 letras), que el signo menos excluye palabras y el máximo de 250 resultados ([GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)). Se usa el código FIPS de Natural Earth (`MX`) y, si un país no lo tiene, su nombre en inglés sin espacios (ADR-0009). `# VERIFICAR:` en F3 que `sourcecountry:MX` devuelve resultados.

**Reglas:**
- **Una consulta por proveedor y concepto.** Las palabras clave se unen con `OR`. Si se excede el límite de longitud del proveedor, se reparten en grupos.
- **El nombre de la región se usa tal cual se escribe en medios.** Se usa `search_terms` de la región o, si está vacío, `name` (con acentos). Para CDMX: `("Ciudad de México" OR CDMX)`; para el estado 15, `("Estado de México" OR Edomex)`, nunca "México" solo. La lista curada vive en `geodata/search_terms.csv` (ADR-0009).
- **Nombres repetidos.** Si un municipio comparte nombre con otro, la consulta exige también su estado (`"Benito Juárez" ("Quintana Roo")`). Las localidades siempre llevan su estado.
- **Exclusiones** con signo menos en los tres proveedores. Las palabras no pueden contener comillas, paréntesis, dos puntos, guion inicial ni `OR`/`AND` sueltos.
- **País seleccionado:** no se agrega lugar a la consulta; se usan los filtros de país e idioma del proveedor.
- **Presupuesto:** máximo de consultas por búsqueda configurable (`MAX_QUERIES_PER_SEARCH`, por defecto 10). La UI muestra la estimación antes de ejecutar.
- **Caché:** una consulta idéntica (proveedor + texto + parámetros) dentro de `QUERY_CACHE_TTL_HOURS` (por defecto 6) no vuelve a gastar créditos.
- **"Probar concepto"** ejecuta `build_queries` sin llamar a ningún proveedor, y solo con los proveedores que recibiría una búsqueda real (los configurados): hoy SearchApi y el índice local.

---

## 8. Proveedores

| Proveedor | Rol | Costo | Notas |
|---|---|---|---|
| **SearchApi** (`engine=google_news`) | Principal: resultados reales de Google News | De pago por búsqueda exitosa; 100 solicitudes gratis de prueba | Llave en `SEARCHAPI_API_KEY`. Hasta `SEARCHAPI_MAX_PAGES` páginas de 10 notas por consulta (3 por defecto); la siguiente solo si la anterior vino llena, 1 crédito por página (ADR-0019). |
| **Índice local** (`indice_local`, ADR-0013 y ADR-0014) | Notas que la ingesta periódica junta cada 15 minutos: **ngramas de GDELT** (texto completo, español + México; ADR-0014), archivos GKG de GDELT (solo título; apagados por defecto cuando los ngramas funcionan) y RSS de medios mexicanos activos en `fuentes/medios_rss.csv` | Gratis (consume ~1 GB de descarga al día) | Busca en título, fragmento y frases del cuerpo (`body_terms`, solo para buscar; nunca se muestran). Devuelve candidatos que F4 confirma y geolocaliza con INEGI. Citar "GDELT Project" con link cuando se muestren sus datos. |
| **GDELT DOC 2.0** | Volumen y cobertura amplia de medios en español. ⚠️ **Desactivado por defecto** (`GDELT_ENABLED=false`, ADR-0012): respondió 429 de forma persistente y `{}` después de los rechazos. Se propone reactivarlo cuando `make gdelt-diagnostico` registre notas reales en 2 días distintos; Benji decide. | Gratis | Ventana móvil de los últimos 3 meses, según su documentación. Un `{}` recibido después de un 429 se registra como falla, nunca como "sin resultados". |
| **Google News RSS** | ⚠️ **Fuera de producción** (ADR-0011): sus términos solo permiten uso personal y no comercial. Desactivado por defecto (`NEWS_RSS_ENABLED=false`); solo para desarrollo. | Gratis | Sin garantía de servicio. Ver la nota de abajo sobre sus links. `after:`/`before:` no se respetan: el adaptador descarta notas fuera del rango. |

**Nota sobre los links de Google News RSS:** los links del feed apuntan a `news.google.com` con un identificador codificado. No son redirecciones HTTP simples, así que obtener la URL real del medio no es trivial y puede romperse sin aviso. `# VERIFICAR:` en F3 si existe una forma estable de resolverlos. Si no la hay, las notas de RSS se deduplican solo por título normalizado y fecha (regla de casi duplicado de la sección 9) y la tarjeta muestra el link de Google News.

**Contrato común — `RawArticle`:**

```json
{
  "provider": "searchapi",
  "provider_rank": 3,
  "url": "https://www.medio.com.mx/seguridad/ataque-ransomware-alcaldia-2026",
  "title": "Alcaldía sufre ataque de ransomware; servicios en línea suspendidos",
  "source_name": "Medio Ejemplo",
  "source_domain": "medio.com.mx",
  "published_at": "2026-10-12T14:05:00Z",
  "snippet": "La alcaldía informó que sus sistemas...",
  "language": "es",
  "raw": { "...": "respuesta original del proveedor, para depurar" }
}
```

`source_domain` es el dominio del medio: en Google News RSS el `url` es de Google y el medio llega aparte (`<source url="…">`). Fechas siempre en UTC; si el proveedor no da fecha, `published_at` queda vacío (nunca se inventa).

Cada adaptador debe:
1. usar timeout explícito;
2. reintentar con backoff exponencial ante 429/5xx;
3. no reintentar ante 4xx de autenticación;
4. traducir los errores a excepciones de dominio;
5. registrar en `provider_queries`;
6. tener pruebas con respuestas grabadas.

**Que falle un proveedor no tumba la búsqueda:** la búsqueda queda en `partial` y la UI lo indica.

---

## 9. Pipeline de una búsqueda

Lo ejecuta el worker. Cada etapa actualiza `searches.progress` para que la UI muestre avance real.

1. **Planear.** `build_queries` por cada concepto × proveedor. Se guardan en `provider_queries`.
2. **Consultar.** En paralelo, con límite de concurrencia por proveedor. Primero se revisa la caché. Incluye el índice local (ADR-0013), que responde al instante con lo que la ingesta periódica ya juntó y no pasa por la caché (cambia cada 15 minutos).
3. **Normalizar y deduplicar.**
   - URL canónica: resolver redirecciones, quitar parámetros de rastreo (`utm_*`, `fbclid`...), normalizar dominio.
   - Duplicado exacto: misma URL canónica.
   - Casi duplicado: título normalizado con similitud ≥ 0.9 (rapidfuzz) y misma fecha ±1 día. Se conserva uno y se registran todos los proveedores que lo encontraron.
   - Si la noticia ya existe en `articles` (de una búsqueda anterior), se reutiliza su enriquecimiento cuando el `prompt_version` coincide.
4. **Extraer texto** con trafilatura, con concurrencia limitada y timeout. Si falla, se usa título + snippet y se marca `extraction_status = fallback`. El texto solo sirve para procesar: va a `article_texts` y se borra a los `ARTICLE_TEXT_RETENTION_DAYS` días (ADR-0015).
5. **Enriquecer con LLM** (sección 10).
6. **Geolocalizar** (sección 11).
7. **Filtrar por región.** Se calcula `in_region` por prefijo de código. Las noticias fuera de región **no se borran**: se muestran aparte.
8. **Cerrar.** Se asigna el status final, se registran créditos usados y se escribe en la bitácora.

Los errores por noticia van a `processing_errors` y no detienen el resto. Si más del 50% de las noticias falla en una etapa, la búsqueda queda en `partial` con resumen del error.

---

## 10. Enriquecimiento con LLM

- **Modelo:** configurable. `LLM_PROVIDER` elige `openai` (por defecto, `gpt-6-luna`; ADR-0016) o `gemini` (`gemini-2.5-flash`). Ambos cumplen `LLMPort` y comparten prompt y validación.
- **Prompts:** se guardan versionados en `adapters/llm/prompts/` (vigentes: `enrich_v2.md`, que agrega `municipality_hint` para colonias y calles, ADR-0020; `summary_v1.md` para el reporte; `entities_v1.md` para las entidades de un caso, §10.1). Cambiar el prompt implica subir la versión, y las notas leídas con otra versión se vuelven a leer.
- **Salida:** JSON validado con Pydantic. Si no valida, se reintenta una vez con el error incluido; si vuelve a fallar, va a `processing_errors`.
- **Caché:** por (`text_hash`, `prompt_version`, `concept_ids`).
- **Costo (ADR-0015):** antes de gastar se estima y se muestra; tope de `LLM_MAX_ARTICLES_PER_SEARCH` (150) notas por búsqueda; se registran tokens y costo estimado por búsqueda.

**Salida esperada:**

```json
{
  "concepts": [
    {
      "concept_id": 1,
      "is_relevant": true,
      "relevance_score": 0.93,
      "relevance_reason": "Describe un ataque de ransomware contra los sistemas de una alcaldía."
    }
  ],
  "summary": "La alcaldía Iztapalapa reportó un ataque de ransomware que suspendió sus trámites en línea. Las autoridades indicaron que no hubo robo de datos personales confirmado.",
  "event_type": "ransomware",
  "event_date": "2026-10-11",
  "locations": [
    {
      "mention": "Iztapalapa",
      "kind_hint": "municipality",
      "state_hint": "Ciudad de México",
      "municipality_hint": "Iztapalapa",
      "country": "México",
      "role": "event"
    }
  ]
}
```

**Reglas del prompt:**
- **No inventar.** Si un dato no está en el texto, va `null`.
- **Resumen:** 2–3 oraciones, neutral, en español, sin copiar frases textuales largas.
- **Relevancia estricta.** "Secuestro" en sentido figurado ("secuestraron la agenda legislativa") no es relevante. Tampoco lo son cursos, webinars u ofertas de empleo.
- **`role`:** `event` es donde ocurrió el hecho; `mentioned` es solo una mención (por ejemplo, la sede de la empresa afectada o el lugar desde donde declaró un funcionario).

### 10.1 Entidades de las notas de un caso (Fase 9.4, ADR-0103)

Las entidades (personas, organizaciones, lugares y vehículos) **no** salen del enriquecimiento de cada búsqueda: se piden en una llamada aparte, solo para las notas que entran a un caso (`EntityExtractorPort`, prompt `entities_v1.md`).

- **Una vez por nota y versión de prompt** (`entity_extractions`); si la nota entra a otro caso se reutiliza sin volver a pagar.
- **Texto:** el cuerpo extraído y recortado (`text_for_llm`); si ya se borró a los 30 días, título y fragmento del medio, y se marca `title_snippet`. El resumen propio nunca se usa como evidencia.
- **Salida (validada con Pydantic, un reintento):** `{"entities": [{type, label, aliases, role, legal_status_hint, confidence, evidence_span}]}`. En OpenAI el esquema estricto solo admite los tipos `person`, `org`, `place`, `vehicle` y los siete estatus legales.
- **Revisión contra el texto** (`domain/entity_extraction.py`): se descarta, con su motivo, la propuesta cuya cita no aparece literal en lo que leyó la IA o cuyo nombre no está escrito en la nota. La cita que se guarda es la del texto, recortada a 300 caracteres.
- **Agrupación en el caso:** las propuestas con el mismo tipo y el mismo nombre de comparación forman una sola sugerencia. El nombre de comparación (`entity_name_norm`, Fase 9.5) es el `name_norm` del proyecto sin comillas: "Eduardo “N”", "Eduardo 'N'" y "Eduardo N" son el mismo.
- **Reglas del prompt:** solo lo que dice el texto; la nota es aislada (no se cruza con otras notas ni bases); el estatus legal es lo que afirma la nota y nunca "culpable"; cada entidad con su cita literal; todo entra como sugerido.

### 10.2 Resolución de entidades de un caso (Fase 9.5, ADR-0104)

El sistema **sugiere** qué entidades del caso podrían ser la misma; **solo una persona las une** (nunca se fusiona solo, ni entre casos).

- **Cuándo se sugiere** (`domain/entity_resolution.py`): dos entidades del mismo caso y tipo, no unidas a otra, no descartadas y visibles, si tienen el mismo nombre de comparación, un nombre o alias en común (contando los de lo que ya se les unió) o nombres con trigramas ≥ 0.9. Se calcula al leer; «No son la misma» se guarda en `entity_merge_dismissals` y el par no vuelve.
- **Unir:** solo se escribe `merged_into` en la que se une; menciones, alias y vínculos no se mueven. Las lecturas muestran la que queda con la evidencia de todo su grupo. Si una está confirmada, esa es la que queda; lo descartado no se une.
- **Deshacer:** «Separar» borra el `merged_into` (lo que se le había unido a ella se va con ella). «Separar menciones» pasa menciones propias a una sugerencia nueva, para cuando la agrupación juntó a dos personas con el mismo nombre.
- **Bitácora:** `entity.merged`, `entity.unmerged`, `entity.split` y `entity.merge_dismissed`, con quién y qué quedó.

### 10.3 Vínculos entre entidades de un caso (Fase 9.5)

Solo entre entidades **confirmadas** del caso (cada una como la raíz de su grupo de fusión).

- **Coocurrencia** (`domain/relationships.py`): dos entidades confirmadas que aparecen en la misma nota del caso forman «aparecen juntas», sugerido, con confianza 0.5 (una nota), 0.7 (dos) o 0.9 (tres o más). Se calcula al leer: confirmar, unir, separar o quitar una nota se refleja sin refrescar. Se guarda en `relationships` solo al confirmarlo o descartarlo; lo descartado no vuelve.
- **Dibujado por el analista:** cualquier tipo (`family`, `associate`, `employer`, `located_in`, `owns`, `same_event`, `appears_with` o `custom` con su etiqueta de hasta 80 caracteres) y una nota opcional. Nace confirmado, con origen `human`, confianza 1 y la firma de quien lo dibuja. Los simétricos se guardan con el id menor primero; los dirigidos respetan el sentido. Si ya existía con las mismas entidades y tipo, se confirma ese.
- **Evidencia:** cada vínculo muestra las notas del caso donde aparecen las dos entidades.
- **Bitácora:** `relationship.created`, `relationship.confirmed` y `relationship.discarded`.

### 10.4 El muro de un caso sobre el globo (Fase 9.6, H9.3)

- **Entrada:** «🌐 Ver en el globo» en el detalle del caso, un marcador de «Mis casos» en Explorar o la URL `#/explorar?caso=<id>`. El globo deja de mostrar la búsqueda y dibuja el muro; «✕ Salir del muro» regresa.
- **Qué se dibuja** (`GET /cases/{id}/graph`): solo entidades confirmadas (ADR-0104), hasta `CASE_MAX_VISIBLE_NODES` (150); los vínculos no descartados (sugeridos punteados).
- **Dónde** (`domain/case_graph.py`): un lugar va a su punto del catálogo; lo demás va al lugar más repetido de sus notas, repartido en espiral (determinista) para que no se encime. Es una posición visual, no un domicilio, y el panel lo dice.
- **Cámara:** al abrir encuadra todo; al elegir una entidad la orbita, atenúa lo demás y muestra su panel (estatus legal, vínculos, citas). Esc regresa.
- **Constelación:** las notas del caso unidas por las entidades confirmadas que comparten.
- **Bitácora:** abrir el muro es ver el caso (`case.viewed`, una vez cada 5 minutos por persona).
- **«Limpiar globo» / «Nueva búsqueda»:** quitan resultados, nota y muro y vuelven a México con el formulario listo.

---

## 11. Geolocalización

### Algoritmo para cada mención

1. **País distinto de México:** resolver a la región `country`. Fin.
2. **Normalizar** la mención: mayúsculas, sin acentos, conservando Ñ, y sin la palabra genérica del inicio ("alcaldía", "colonia", "calle"…; ADR-0020). Aplicar alias (`CDMX` → `CIUDAD DE MEXICO`; `EDOMEX` → `MEXICO`, estado 15; `LA CAPITAL DEL PAIS` → estado 09).
3. **Coincidencia exacta** de `name_norm`, en el nivel sugerido y, si hay `state_hint`, **solo** dentro de ese estado: un homónimo de otro estado nunca gana.
4. **Varias coincidencias.** Desempatar en este orden:
   1. otras menciones del mismo artículo con estado;
   2. la región buscada;
   3. la población (solo como último recurso y con confianza baja).

   Si sigue ambigua, **no asignar ese nivel**: subir al nivel común (estado si todas coinciden en uno) o marcar `unknown`.
5. **Sin coincidencia exacta:** similitud trigram ≥ 0.85 con confianza reducida.
   - Si tampoco: **colonias de OpenStreetMap** (`places`, ADR-0020) del estado conocido, por nombre exacto o familia, solo si todas caen en un municipio (o en el que sugiere la IA). Precisión `locality`, punto de la colonia.
   - Si tampoco y la IA dio el estado: el estado, con confianza 0.6 (aproximada).
6. **Ubicación principal:** la mención `role=event` más específica con confianza ≥ umbral (`GEO_MIN_CONFIDENCE`, por defecto 0.6), prefiriendo las que caen dentro de la región buscada. Si no hay ninguna, la mención `role=mentioned` más específica dentro de la región buscada (la ficha dice "lugar mencionado").
7. **Punto para el mapa:** coordenadas de la localidad o centroide de la región. **Nunca coordenadas inventadas por el LLM.**

### Casos de prueba obligatorios

Se escriben como pruebas unitarias con un catálogo de prueba.

| Mención | Contexto | Resultado esperado |
|---|---|---|
| "Iztapalapa" | — | Municipio Iztapalapa (CDMX), precisión `municipality`, mostrado como "Alcaldía Iztapalapa" |
| "San Pedro Garza García" | — | Municipio en Nuevo León |
| "San Pedro" | El artículo menciona "Coahuila" | San Pedro, Coahuila |
| "San Pedro" | Sin otra pista | Ambigua: no se asigna municipio; confianza baja |
| "CDMX" / "la capital del país" | — | Estado 09, precisión `state` |
| "Edomex" | — | Estado 15 |
| "Nezahualcóyotl" / "Neza" | — | Municipio en el Estado de México (alias "Neza") |
| "Madrid" | Ataque en España | País España, `in_region = false` si se buscó en México |
| "Peñón de los Baños" | — | Comparación correcta con Ñ, sin convertirla en N |
| "Polanco" (estado CDMX) | La nota también nombra Jalisco | Colonia Polanco, Alcaldía Miguel Hidalgo; nunca la localidad Polanco de Jalisco |
| "alcaldía Iztapalapa" | — | Municipio Iztapalapa |
| "calle Molière" (estado CDMX) | — | Estado 09, aproximada |
| "El Rosario" (estado Sinaloa) | — | Municipio Rosario (INEGI lo registra sin artículo) |
| (búsqueda en la localidad "Miguel Hidalgo") | Nota en Polanco | Dentro de la región: la localidad cabecera homónima vale por su alcaldía |
| (sin lugar) | — | Precisión `unknown`; no se pinta en el mapa y aparece en la lista "Sin ubicación" |

---

## 12. Geodatos

**Fuentes**

| Uso | Fuente |
|---|---|
| México | **INEGI — Marco Geoestadístico**, edición más reciente disponible: capas de entidades, municipios y localidades (polígonos urbanos y puntos rurales). |
| Países | **Natural Earth** (dominio público), escala 1:10m o 1:50m. |
| Mapa base | **Protomaps** (OpenStreetMap) en PMTiles, extracto de México + mundo a baja resolución. |

**Pipeline** (`geodata/scripts/`, idempotente, con README)

1. **Descargar** a `geodata/raw/`, registrando URL, fecha y edición.
2. **Detectar encoding** de los atributos y validar con 5 ejemplos con Ñ y acentos (por ejemplo "Peñón", "Nezahualcóyotl").
3. **Reproyectar.** INEGI viene en cónica conforme de Lambert; leer el `.prj` (ediciones recientes usan EPSG:6372) y reproyectar a EPSG:4326.
4. **Validar y reparar geometrías** (`ST_MakeValid`).
5. **Cargar a PostGIS a resolución completa**, en lotes, para las consultas espaciales.
6. **Generar PMTiles para el navegador** con geometrías simplificadas por nivel de zoom (tippecanoe):

| Capa | Zoom visible |
|---|---|
| países | 0–6 |
| estados | 2–10 |
| municipios | 5–14 |
| localidades (puntos) | ≥ 10 |

   Cada feature lleva `code` y `name` para que el click resuelva la región.

**Validación (criterios de aceptación)**
- 32 entidades.
- Número de municipios igual al catálogo INEGI de la edición descargada.
- CDMX con 16 alcaldías.
- Sin geometrías inválidas.
- 5 nombres con Ñ correctos.
- Un punto conocido (por ejemplo, el Zócalo) cae en el estado 09 y en la alcaldía Cuauhtémoc.

---

## 13. API REST (`/api/v1`)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado de API, base de datos, Redis y worker |
| GET | `/regions?level=state` | Lista por nivel |
| GET | `/regions/{id}` y `/regions/{id}/children` | Detalle e hijos (para filtros encadenados) |
| GET | `/regions/search?q=izta` | Búsqueda difusa por nombre |
| GET | `/regions/at?lon=&lat=&level=` | Región en un punto |
| GET/POST/PATCH/DELETE | `/concepts` | CRUD (DELETE es borrado lógico si el concepto tiene búsquedas) |
| POST | `/concepts/preview?region_id=&days=` | Lo mismo con un concepto sin guardar (en el cuerpo), para "Probar concepto" antes de guardar (H2) |
| POST | `/concepts/{id}/preview?region_id=&days=` | Consultas que se generarían, sin gastar créditos |
| POST | `/searches/estimate` | Estimación de consultas y créditos |
| POST | `/searches` | Crea búsqueda → `202 {search_id}` |
| GET | `/searches/{id}` | Estado y progreso |
| GET | `/searches` | Historial (paginación por cursor) |
| GET | `/searches/{id}/articles?cursor=&limit=&relevant=&in_region=&precision=&concept_id=` | Resultados (paginación por cursor). Por defecto solo las relevantes (`relevant=all` trae todas); `in_region` = `true`, `false` o `none` (sin ubicación) |
| GET | `/searches/{id}/aggregates?level=state\|municipality\|locality\|country` | Conteo por región para el mapa de calor. Las notas menos precisas que el nivel no se reparten (`coarser`). `locality` lo usan los reportes de un municipio |
| GET | `/articles/{id}` | Detalle |
| POST | `/searches/{id}/report?format=pdf\|html` | Genera reporte (`409` si la búsqueda no ha terminado) |
| GET | `/searches/{id}/export?format=csv\|geojson` | Notas de la búsqueda como datos: metadatos, resumen y link, nunca el texto completo |

Errores con formato uniforme: `{ "error": { "code": "...", "message": "...", "details": {} } }`, con mensajes en español. También ante fallas inesperadas (`500 internal_error`) y configuración faltante (`503`, por ejemplo `llm_not_configured`). Ejemplos con `curl` en `docs/api.md`.

---

## 14. Frontend

### 14.1 Pantallas

1. **Explorar** (principal): globo + panel de búsqueda + resultados.
2. **Conceptos:** tabla + formulario + "Probar concepto".
3. **Historial:** búsquedas anteriores, reabrir y comparar.

### 14.2 Comportamiento del globo

**Apariencia (ADR-0017)**
- El globo ocupa la pantalla, sobre un fondo de universo (Vía Láctea y estrellas que titilan) que gira con la cámara.
- Tierra con textura satelital de la NASA. Por defecto de noche, con las ciudades iluminadas; un botón cambia a la de día. Al acercarse se funde con el mapa de calles y los límites de INEGI.
- Paneles translúcidos a la izquierda (búsqueda, lista y descargas) que no tapan el centro; la derecha queda libre para el globo.

**Vista inicial**
- La cámara entra desde lejos y llega a México con frenado suave (~3.5 s).
- Proyección `globe`, rotación lenta automática centrada en México (una vuelta en 90 s, más lenta al acercarse).
- La rotación se detiene al interactuar y hay un botón para reanudarla. Se reanuda sola tras 25 s sin uso, acelerando poco a poco.

**Movimiento**
- Los vuelos duran según la distancia y el cambio de zoom (1.2 a 4.5 s). Subir por las migas de pan es más rápido.
- Control de velocidad: lenta, normal, rápida o sin animación. Se recuerda en el navegador. Si el sistema pide menos movimiento, no hay animaciones.

**Interacción**
- **Hover:** resalta la región bajo el cursor y muestra un tooltip con nombre y tipo ("Alcaldía Iztapalapa").
- **Click en país:** selecciona el país. Si es México, la cámara vuela y se muestran los estados.
- **Click en estado:** vuela al `focus_bbox` (encuadre medido sobre la esfera, no en el mapa plano), resalta y muestra los municipios.
- **Click en municipio:** lo selecciona; con más zoom aparecen las localidades.
- **Click en localidad:** la selecciona.

**Sincronización**
- **Migas de pan:** México › Ciudad de México › Iztapalapa. Cada nivel es clickeable para subir.
- **Filtros encadenados** (Estado → Municipio → Localidad) con buscador. Cambiar el filtro mueve el mapa y viceversa: hay una sola fuente de verdad en el store.

**Resultados en el mapa**
- **Mapa de calor** según el nivel visible.
- **Marcadores agrupados** (clusters).
- **Precisión visible:** las noticias ubicadas solo a nivel estado o país se dibujan en el centroide con un estilo distinto (anillo punteado) y una leyenda, para no hacer creer que ocurrieron en el centro exacto.
- **Click en noticia** (lista o mapa): vuela al punto y abre la tarjeta.

**Rendimiento**
- Las geometrías llegan siempre por PMTiles. Nunca se descargan GeoJSON pesados al navegador.
- Objetivo: 60 fps al rotar en un equipo de oficina.

### 14.3 Panel de búsqueda

- Región seleccionada.
- Conceptos (chips multiselección, solo activos).
- Rango de fechas: hoy, 7 días, 30 días o personalizado.
- Estimación ("3 consultas · ~1 crédito").
- Botón **Buscar**.
- Barra de progreso por etapas.

### 14.4 Tarjeta de noticia

- Título.
- Medio y fecha (hora de CDMX).
- Concepto(s) con color.
- Resumen generado, marcado como "Resumen automático".
- Ubicación con insignia de precisión.
- Botón "Ver nota original" (abre en otra pestaña).
- Proveedores que la encontraron.

### 14.5 Estilo y accesibilidad

- Modo oscuro por defecto (uso prolongado), con alternativa clara.
- Contraste AA y navegación con teclado en paneles y filtros.

---

## 15. Reportes

Plantilla Jinja2 única → HTML (vista previa) y PDF (WeasyPrint).

**Contenido:**
- portada: conceptos, región, rango, fecha y hora de generación, usuario;
- resumen ejecutivo generado por el LLM a partir de los resúmenes, nunca del texto completo;
- tabla de conteo por subregión (país → estados, estado → municipios, municipio → localidades; lo menos preciso se cuenta aparte);
- mapa estático en SVG dibujado en el servidor con PostGIS: subregiones coloreadas por número de notas y puntos, con anillo punteado para lo poco preciso (ADR-0018);
- lista de noticias con resumen, fuente, fecha, link y precisión;
- pie con proveedores consultados y créditos usados.

El resumen ejecutivo se guarda en `reports` y no se vuelve a pagar. La fuente (Noto Sans) va incluida en el repositorio para que la Ñ y los acentos salgan iguales en cualquier servidor.

**Datos:** CSV (UTF-8 con BOM, para Excel) y GeoJSON (un punto por nota ubicada), con metadatos, resumen generado y link. Cada reporte o exportación queda en la bitácora como `report.generated`.

---

## 16. Seguridad y auditoría

- Hasta la Fase 8, un usuario de desarrollo fijo. En la Fase 8: autenticación (JWT, con opción de integrarse al sistema de identidad principal), roles `admin` (gestiona conceptos) y `analyst` (busca y genera reportes), y límite de búsquedas por usuario y hora.
- La bitácora de auditoría registra: crear, editar o eliminar conceptos, cada búsqueda con sus parámetros y créditos, y cada reporte generado.
- CORS restringido. Encabezados de seguridad en nginx.

---

## 17. Fases

Cada fase termina con criterios verificables, `CHANGELOG.md` actualizado y tag. No se avanza sin aprobación.

### F0 — Cimientos

**Tareas**
- **Verificar entorno:** SO, WSL, Python, Node y espacio en disco. Si algo no funciona, **detenerse y reportar**.
- **Repositorio:** estructura de carpetas, `pyproject.toml`, configuración de ruff, mypy y pytest, `package.json` con Vite, ESLint, Prettier y Tailwind, pre-commit, Makefile.
- **Servicios (sin Docker, ver ADR-0006):** script idempotente que instala en Ubuntu (WSL) PostgreSQL 16 + PostGIS, Redis, nginx y Python 3.12 (con `uv`), y comandos `make up` / `make down` / `make status` que arrancan y detienen postgres, redis, api, worker y nginx.
- **Configuración y diagnóstico:** `.env.example` documentado y `/health` funcional.
- **Documentación:** README con instrucciones de arranque desde cero y ADRs iniciales (ver sección 18).

**Criterios de aceptación**
- `make up` levanta todo.
- `/health` responde OK para todos los componentes.
- `make test` y `make lint` pasan.
- Un desarrollador nuevo puede arrancar el proyecto siguiendo solo el README.

### F1 — Geodatos

**Tareas**
- Pipeline completo de la sección 12.
- Tabla `regions` con su migración.
- Endpoints `/regions/*`.

**Criterios de aceptación**
- Las validaciones de la sección 12 pasan.
- `/regions/search?q=izta` devuelve Iztapalapa.
- `/regions/at` con las coordenadas del Zócalo devuelve Cuauhtémoc.
- Los PMTiles se generan y nginx los sirve con soporte de Range (verificar con `curl -I -H "Range: bytes=0-100"`).

### F2 — Conceptos

**Tareas**
- Dominio, CRUD, validaciones (nombre único, al menos una palabra clave, sin duplicados de palabras clave), borrado lógico, seed, `build_queries` y endpoint `preview`.

**Criterios de aceptación**
- Pruebas unitarias de `build_queries` con los casos de la sección 7.2.
- CRUD probado de punta a punta.

### F3 — Proveedores e ingesta

**Tareas**
- Puerto `NewsProviderPort` y los 3 adaptadores.
- Normalización a `RawArticle`, caché, contador de créditos y presupuesto.
- Pruebas con fixtures.
- Comando `make probar-proveedor` (`backend/app/cli/probar_proveedor.py`, con tipos y pruebas como el resto del backend) que ejecuta **una** consulta real con confirmación previa y guarda la respuesta como fixture, sin la llave.
- Ingesta periódica (cada 15 min, `celery beat`) de archivos GKG de GDELT y RSS de medios mexicanos a un índice local, y proveedor `indice_local` que busca en él (ADR-0013).
- Ngramas de GDELT (texto completo de las notas) como fuente del índice local, `make ingesta-historial` y una pestaña temporal "Notas" para ver el índice en la interfaz hasta F6 (ADR-0014).

**Criterios de aceptación**
- Pruebas sin red pasan.
- Una consulta real a SearchApi, aprobada por Benji, devuelve resultados normalizados.
- La ingesta de GDELT y de RSS de medios funciona con datos reales y se muestran 5 ejemplos de cada una.
- `indice_local` responde a los casos de §7.2 sobre el índice real.

### F4 — Pipeline, LLM y geolocalización

**Tareas**
- Etapas 1–8 de la sección 9 en Celery.
- Adaptador de LLM con prompt versionado.
- Resolutor geográfico con los casos de la sección 11.
- Tabla `processing_errors`.
- Comando `make buscar` que corre una búsqueda real de punta a punta (pide confirmación con el costo estimado) y muestra 5 ejemplos. Los endpoints de búsqueda llegan en F5.

**Criterios de aceptación**
- Todos los casos de prueba de la sección 11 pasan.
- Una búsqueda real de punta a punta (aprobada) termina en `completed` con noticias clasificadas y ubicadas.
- Se muestran 5 ejemplos con su ubicación y precisión para validación manual.

### F5 — API de búsqueda y resultados

**Tareas**
- Endpoints de búsquedas, resultados, agregados e historial.
- Paginación por cursor.
- Formato de errores uniforme.
- OpenAPI revisado.

**Criterios de aceptación**
- Pruebas de integración de todos los endpoints.
- `docs/api.md` con ejemplos de `curl`.

### F6 — Frontend: globo y búsqueda

**Tareas**
- Todo lo de la sección 14.
- Retirar la pestaña temporal "Notas" y sus rutas `/local-index/*` (ADR-0014). El índice local sigue siendo uno de los proveedores de las búsquedas.

**Criterios de aceptación**
- La historia H1 se puede ejecutar completa en el navegador.
- Mapa y filtros siempre sincronizados.
- Rotación fluida.
- Prueba de humo del flujo principal.

### F7 — Reportes

**Tareas**
- Todo lo de la sección 15.

**Criterios de aceptación**
- La historia H5 genera un PDF correcto, con acentos y Ñ bien renderizados.

### F8 — Endurecimiento e integración

**Tareas**
- Autenticación, roles, límites de uso y auditoría completa.
- Monitoreo programado (búsquedas recurrentes).
- Guía de despliegue.
- Documentación para integrar el módulo con el sistema principal y n8n.

**Criterios de aceptación**
- A definir con Benji al llegar a esta fase.

---

## 18. ADRs iniciales (Fase 0)

1. **ADR-0001** — Arquitectura hexagonal y convención de idioma (identificadores en inglés, documentación en español).
2. **ADR-0002** — PostgreSQL + PostGIS como única base de datos y catálogo `regions` unificado con claves INEGI.
3. **ADR-0003** — Estrategia multiproveedor de noticias. Por qué no se usa la Custom Search JSON API de Google: cerrada a clientes nuevos y con fecha de descontinuación el 1 de enero de 2027.
4. **ADR-0004** — MapLibre GL (globo) + PMTiles autoalojados frente a alternativas (CesiumJS, deck.gl, react-globe.gl).
5. **ADR-0005** — Celery + Redis para procesamiento asíncrono.
6. **ADR-0006** — Entorno de desarrollo sin Docker: servicios nativos en WSL, Python 3.12 con `uv` y PostgreSQL 16 del repositorio oficial.

ADRs de la Fase 1:

7. **ADR-0007** — MapLibre GL JS v6 en lugar de v5.
8. **ADR-0008** — Fuentes y procesamiento de geodatos (edición INEGI, geometría de México, punto representativo, nombres y códigos de países).

ADR de la Fase 2:

9. **ADR-0009** — Construcción de consultas a los proveedores (dialectos, términos de búsqueda de cada lugar, nombres repetidos, códigos de país).

ADR de la Fase 3:

10. **ADR-0010** — httpx2 (continuación mantenida de httpx) para las llamadas externas y `MockTransport` para sus pruebas, en lugar de httpx + respx.
11. **ADR-0011** — Google News RSS fuera de producción por sus términos de uso (desactivado por defecto).
12. **ADR-0012** — GDELT desactivado mientras responda 429 de forma persistente; criterio de reactivación con el reintento diario de D1.
13. **ADR-0013** — Ingesta periódica e índice local de notas (archivos GKG de GDELT y RSS de medios mexicanos).
14. **ADR-0014** — Ngramas de GDELT como fuente del índice local (la API DOC está saturada).
15. **ADR-0015** — Extracción de texto, su retención y el control de costo de la IA.
16. **ADR-0016** — OpenAI como IA del enriquecimiento, elegible junto a Gemini.

---

## 19. Riesgos y preguntas abiertas

| Tema | Riesgo o pregunta | Mitigación |
|---|---|---|
| Entorno | Docker no funciona en el equipo de desarrollo (Windows 11 21H2 con WSL integrado antiguo). | **Decidido en F0 (ADR-0006):** servicios nativos en Ubuntu dentro de WSL, código en Windows. Sin Docker se pierde el aislamiento, así que las versiones se fijan con el repositorio oficial de PostgreSQL y con `uv.lock`. El despliegue final (F8) puede usar contenedores o una VM Linux sin cambiar el código. |
| Costos | Consumo de créditos de SearchApi y Gemini. | Estimación previa, presupuesto por búsqueda, caché, bitácora de créditos. |
| Calidad geográfica | Las notas rara vez mencionan colonias; muchas solo dicen el estado. | La precisión es explícita y visible; nunca se finge más detalle del que hay. |
| Proveedores | Cambios de API o precio. | Puertos y adaptadores; tres fuentes independientes. |
| Derechos de autor | Contenido de los medios. | Solo metadatos, resumen propio y link; el texto completo no se expone. |
| Integración | Autenticación del sistema principal. | La API queda versionada; la autenticación se diseña en F8. |
| Versiones del frontend | Ya existe React 19 y Tailwind v4 cambió su forma de configurarse respecto a v3. | Se respeta React 18 tal como dice la sección 5.4. Subir a React 19 requiere un ADR. Tailwind se usa en su versión estable vigente. |
| Links de Google News RSS | Son identificadores codificados, no redirecciones simples (ver sección 8). | Deduplicar por título y fecha si no se pueden resolver; se decide en F3. |

---

## 20. Pendientes y mejoras futuras

Ideas registradas para evaluarlas después. **No están en el alcance de ninguna fase** hasta que Benji las apruebe.

| Idea | Por qué podría servir | Qué habría que evaluar antes |
|---|---|---|
| **Ingerir los archivos GKG de GDELT** en lugar de su API DOC 2.0 (Benji, 16/10/2026). ✅ **Aprobado e incorporado a F3** (ADR-0013); quedan por evaluar el uso de sus temas y el historial largo. | GDELT publica sus datos como archivos descargables que se actualizan cada 15 minutos. El GKG (Global Knowledge Graph) trae cada nota con **temas ya clasificados** y **ubicaciones ya geocodificadas**. Podría evitar el límite de la API (ADR-0012) y adelantar parte del trabajo de clasificación y geolocalización de F4. | `# VERIFICAR:` en la documentación vigente de GDELT: formato y campos exactos del GKG, tamaño de los archivos y espacio en disco, cobertura de medios mexicanos en español, calidad de sus ubicaciones frente al catálogo INEGI (§11), términos de uso y si conviene un proceso programado (F8). |

## 21. Historial del documento

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0 | Octubre 2026 | Versión inicial. |
| 1.1 | 15 de octubre de 2026 | Campo `aliases`/`aliases_norm` en `regions`; filtro `sourcecountry` en GDELT y ventana de 3 meses; nota sobre los links de Google News RSS; riesgos de versiones del frontend. |
| 1.2 | 15 de octubre de 2026 | Entorno de desarrollo sin Docker (ADR-0006): cambian la estructura del repositorio, las tareas de F0 y el riesgo de entorno. |
| 1.3 | 15 de octubre de 2026 | MapLibre GL JS v6 (ADR-0007), decisiones de geodatos (ADR-0008) y lógica del pipeline en `backend/app/geodata/`. |
| 1.4 | 16 de octubre de 2026 | Construcción de consultas (ADR-0009): `search_terms` y códigos de país en `regions`, nombres repetidos con su estado, exclusiones también en GDELT; `name_norm` y `deleted_at` en `concepts`; columnas de entidad en `audit_log`; endpoint `POST /concepts/preview`. |
| 1.5 | 16 de octubre de 2026 | httpx2 en lugar de httpx + respx (ADR-0010); `source_domain` en `RawArticle`; `search_id` opcional y `error_message` en `provider_queries`; comando `make probar-proveedor` en `backend/app/cli/`. |
| 1.6 | 16 de octubre de 2026 | Google News RSS fuera de producción por sus términos de uso (ADR-0011, `NEWS_RSS_ENABLED=false`); GDELT como proveedor no garantizado. |
| 1.7 | 16 de octubre de 2026 | GDELT desactivado por defecto con criterio de reactivación (ADR-0012); un `{}` tras un 429 es falla; nueva sección 20, "Pendientes y mejoras futuras" (GKG de GDELT); el historial pasa a la sección 21. |
| 1.8 | 16 de octubre de 2026 | F3 se amplía a "Proveedores e ingesta": índice local alimentado cada 15 minutos por los archivos GKG de GDELT y RSS de medios mexicanos, consultado por el proveedor `indice_local` (ADR-0013). |
| 1.9 | 16 de octubre de 2026 | Ngramas de GDELT (texto completo) como fuente del índice local, con frases del cuerpo conservadas 30 días; pestaña temporal "Notas" hasta F6 (ADR-0014). |
| 2.0 | 16 de octubre de 2026 | F4: extracción de texto con retención de 30 días y control de costo de Gemini (ADR-0015); comando `make buscar`. |
| 2.1 | 17 de octubre de 2026 | OpenAI (`gpt-6-luna`) como IA por defecto, Gemini elegible con `LLM_PROVIDER` (ADR-0016). |
| 2.2 | 17 de octubre de 2026 | F5: parámetros finales de `/searches/{id}/articles` (`relevant`, `concept_id`, `in_region=none`) y de `/aggregates` (`level`, `coarser`); errores 500 y 503 uniformes; `docs/api.md`. |
| 2.3 | 17 de octubre de 2026 | F6: Tierra realista con texturas de la NASA, fondo de universo con three.js y reglas de movimiento del globo (ADR-0017). |
| 2.4 | 17 de octubre de 2026 | F7: reportes con mapa SVG dibujado en el servidor, resumen ejecutivo guardado en `reports`, fuente incluida y datos en CSV y GeoJSON (`/export`) (ADR-0018). |
| 2.5 | 19 de octubre de 2026 | Explorar sin las gráficas "Top 5 estados" y "Tipos de noticias" (decisión de Benji): la derecha queda libre para el globo. |
| 2.6 | 20 de octubre de 2026 | `regions.focus_bbox` (§6): la cámara encuadra la parte principal de cada región; al elegir Estados Unidos, Rusia o Francia el globo ya no se aleja (§14.2). |
| 2.7 | 21 de octubre de 2026 | SearchApi pide hasta 3 páginas por consulta, solo mientras vengan llenas (§8, ADR-0019). |
| 2.8 | 21 de octubre de 2026 | Geolocalizador: colonias de OpenStreetMap (`places`, `make geo-places`), palabras genéricas, estado de la IA obligatorio y ubicación principal dentro de la región buscada (§6, §11, ADR-0020). |
| 2.9 | 20 de octubre de 2026 | "Probar concepto" muestra solo los proveedores que recibiría la búsqueda (§9); el reporte cuenta "dentro" con la regla de la localidad cabecera homónima (§15, ADR-0020). |
| 2.10 | 21 de octubre de 2026 | Modelo de datos del tablero de investigación (§6, Fase 9.2): entidades, menciones, vínculos, casos y `external_links` reservada (ADR-0101, 0104, 0105). |
