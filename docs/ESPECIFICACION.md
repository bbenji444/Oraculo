# Especificación — Monitor de Noticias Geolocalizadas

Versión 1.0 · Octubre 2026 · Responsable: Benji

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
├── docker-compose.yml
├── .env.example
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
│   ├── scripts/             # descarga, reproyección, simplificación, PMTiles, carga PostGIS
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
| HTTP externo | httpx (async) + tenacity | Timeouts, reintentos con backoff y concurrencia controlada. |
| Extracción de texto | trafilatura | Extrae el cuerpo del artículo sin menús ni anuncios. |
| LLM | Gemini 2.5 Flash vía SDK oficial vigente (`google-genai`; verificar), detrás de `LLMPort` | Ya se usa en el proyecto, es barato y rápido. El puerto permite cambiarlo. |
| Reportes | Jinja2 + WeasyPrint | Una misma plantilla HTML sirve para vista web y para PDF. |
| Frontend | React 18 + TypeScript + Vite | Ecosistema amplio, tipado. |
| Globo y mapa | MapLibre GL JS v5 (proyección `globe`) | Globo 3D rotable que hace zoom continuo hasta nivel calle con la misma librería. Open source, sin llave ni costo. |
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
- `display_prefix` (`Alcaldía`, `Municipio`, `Estado`...)
- `geom` geometry(MultiPolygon, 4326), nulo en localidades sin polígono
- `centroid` geometry(Point, 4326)
- `bbox` (para volar la cámara)
- `population` (si la fuente la trae)
- Índices: GIST(`geom`), GIST(`centroid`), GIN(`name_norm gin_trgm_ops`), BTREE(`level`, `parent_id`), BTREE(`code text_pattern_ops`)

**Truco clave:** la jerarquía INEGI está en el prefijo del código. "¿La noticia ubicada en `09007` está dentro de `09`?" se resuelve con `code LIKE '09%'`, sin geometría.

**`concepts`**
- `id`
- `name` (único)
- `description`
- `keywords` text[]
- `exclude_terms` text[]
- `color` (hex)
- `is_active`
- `created_by`

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
- `id`, `search_id`
- `provider`
- `query_text`, `params` jsonb
- `status`, `http_status`
- `results_count`
- `from_cache`
- `cost_credits`
- `duration_ms`

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
- `action`
- `payload` jsonb
- `ip`
- `created_at`

**`users`** — se crea en la Fase 8; antes, un usuario fijo de desarrollo.

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
| GDELT DOC 2.0 | `(ciberataque OR hackeo OR ransomware OR "filtración de datos" OR phishing) Iztapalapa` · `sourcelang:spanish` · `timespan=7d` · `mode=ArtList` · `format=json` · `maxrecords=250` (verificar operadores) |

**Reglas:**
- **Una consulta por proveedor y concepto.** Las palabras clave se unen con `OR`. Si se excede el límite de longitud del proveedor, se reparten en grupos.
- **El nombre de la región se usa tal cual se escribe en medios.** Se usa `name` (con acentos). Para CDMX se agregan variantes conocidas (`CDMX`, `Ciudad de México`) en un campo `aliases` de la región.
- **País seleccionado:** no se agrega lugar a la consulta; se usan los filtros de país e idioma del proveedor.
- **Presupuesto:** máximo de consultas por búsqueda configurable (`MAX_QUERIES_PER_SEARCH`, por defecto 10). La UI muestra la estimación antes de ejecutar.
- **Caché:** una consulta idéntica (proveedor + texto + parámetros) dentro de `QUERY_CACHE_TTL_HOURS` (por defecto 6) no vuelve a gastar créditos.
- **"Probar concepto"** ejecuta `build_queries` sin llamar a ningún proveedor.

---

## 8. Proveedores

| Proveedor | Rol | Costo | Notas |
|---|---|---|---|
| **SearchApi** (`engine=google_news`) | Principal: resultados reales de Google News | De pago por búsqueda exitosa; 100 solicitudes gratis de prueba | Llave en `SEARCHAPI_API_KEY`. Contar créditos por consulta. |
| **GDELT DOC 2.0** | Volumen y cobertura amplia de medios en español | Gratis | Ventana móvil de meses recientes (verificar límite). Respetar su ritmo de peticiones. |
| **Google News RSS** | Respaldo gratuito | Gratis | Sin garantía de servicio. Los links son redirecciones de `news.google.com` y hay que resolver la URL final del medio antes de deduplicar. |

**Contrato común — `RawArticle`:**

```json
{
  "provider": "searchapi",
  "provider_rank": 3,
  "url": "https://www.medio.com.mx/seguridad/ataque-ransomware-alcaldia-2026",
  "title": "Alcaldía sufre ataque de ransomware; servicios en línea suspendidos",
  "source_name": "Medio Ejemplo",
  "published_at": "2026-10-12T14:05:00Z",
  "snippet": "La alcaldía informó que sus sistemas...",
  "language": "es",
  "raw": { "...": "respuesta original del proveedor, para depurar" }
}
```

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
2. **Consultar.** En paralelo, con límite de concurrencia por proveedor. Primero se revisa la caché.
3. **Normalizar y deduplicar.**
   - URL canónica: resolver redirecciones, quitar parámetros de rastreo (`utm_*`, `fbclid`...), normalizar dominio.
   - Duplicado exacto: misma URL canónica.
   - Casi duplicado: título normalizado con similitud ≥ 0.9 (rapidfuzz) y misma fecha ±1 día. Se conserva uno y se registran todos los proveedores que lo encontraron.
   - Si la noticia ya existe en `articles` (de una búsqueda anterior), se reutiliza su enriquecimiento cuando el `prompt_version` coincide.
4. **Extraer texto** con trafilatura, con concurrencia limitada y timeout. Si falla, se usa título + snippet y se marca `extraction_status = fallback`.
5. **Enriquecer con LLM** (sección 10).
6. **Geolocalizar** (sección 11).
7. **Filtrar por región.** Se calcula `in_region` por prefijo de código. Las noticias fuera de región **no se borran**: se muestran aparte.
8. **Cerrar.** Se asigna el status final, se registran créditos usados y se escribe en la bitácora.

Los errores por noticia van a `processing_errors` y no detienen el resto. Si más del 50% de las noticias falla en una etapa, la búsqueda queda en `partial` con resumen del error.

---

## 10. Enriquecimiento con LLM

- **Modelo:** configurable (`LLM_MODEL`, por defecto `gemini-2.5-flash`).
- **Prompts:** se guardan versionados en `adapters/llm/prompts/enrich_v1.md`. Cambiar el prompt implica subir la versión.
- **Salida:** JSON validado con Pydantic. Si no valida, se reintenta una vez con el error incluido; si vuelve a fallar, va a `processing_errors`.
- **Caché:** por (`text_hash`, `prompt_version`, `concept_ids`).

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

---

## 11. Geolocalización

### Algoritmo para cada mención

1. **País distinto de México:** resolver a la región `country`. Fin.
2. **Normalizar** la mención: mayúsculas, sin acentos, conservando Ñ. Aplicar alias (`CDMX` → `CIUDAD DE MEXICO`; `EDOMEX` → `MEXICO`, estado 15; `LA CAPITAL DEL PAIS` → estado 09).
3. **Coincidencia exacta** de `name_norm`, en el nivel sugerido y, si hay `state_hint`, dentro de ese estado.
4. **Varias coincidencias.** Desempatar en este orden:
   1. otras menciones del mismo artículo con estado;
   2. la región buscada;
   3. la población (solo como último recurso y con confianza baja).

   Si sigue ambigua, **no asignar ese nivel**: subir al nivel común (estado si todas coinciden en uno) o marcar `unknown`.
5. **Sin coincidencia exacta:** similitud trigram ≥ 0.85 con confianza reducida.
6. **Ubicación principal:** la mención `role=event` más específica con confianza ≥ umbral (`GEO_MIN_CONFIDENCE`, por defecto 0.6).
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
| POST | `/concepts/{id}/preview?region_id=&days=` | Consultas que se generarían, sin gastar créditos |
| POST | `/searches/estimate` | Estimación de consultas y créditos |
| POST | `/searches` | Crea búsqueda → `202 {search_id}` |
| GET | `/searches/{id}` | Estado y progreso |
| GET | `/searches` | Historial (paginación por cursor) |
| GET | `/searches/{id}/articles?cursor=&limit=&in_region=&precision=` | Resultados (paginación por cursor) |
| GET | `/searches/{id}/aggregates?level=` | Conteo por región para el mapa de calor |
| GET | `/articles/{id}` | Detalle |
| POST | `/searches/{id}/report?format=pdf\|html` | Genera reporte |

Errores con formato uniforme: `{ "error": { "code": "...", "message": "...", "details": {} } }`, con mensajes en español.

---

## 14. Frontend

### 14.1 Pantallas

1. **Explorar** (principal): globo + panel de búsqueda + resultados.
2. **Conceptos:** tabla + formulario + "Probar concepto".
3. **Historial:** búsquedas anteriores, reabrir y comparar.

### 14.2 Comportamiento del globo

**Vista inicial**
- Proyección `globe`, rotación lenta automática centrada en México.
- La rotación se detiene al interactuar y hay un botón para reanudarla.

**Interacción**
- **Hover:** resalta la región bajo el cursor y muestra un tooltip con nombre y tipo ("Alcaldía Iztapalapa").
- **Click en país:** selecciona el país. Si es México, la cámara vuela y se muestran los estados.
- **Click en estado:** vuela al `bbox`, resalta y muestra los municipios.
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
- tabla de conteo por subregión;
- mapa estático (imagen generada en el servidor o captura del canvas enviada por el frontend; decidir en ADR);
- lista de noticias con resumen, fuente, fecha, link y precisión;
- pie con proveedores consultados y créditos usados.

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
- **Verificar entorno:** SO, Docker, Docker Compose, Python, Node y espacio en disco. Si Docker no funciona, **detenerse y reportar**.
- **Repositorio:** estructura de carpetas, `pyproject.toml`, configuración de ruff, mypy y pytest, `package.json` con Vite, ESLint, Prettier y Tailwind, pre-commit, Makefile.
- **Servicios:** `docker-compose.yml` con postgres+postgis, redis, api, worker y nginx.
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

### F3 — Proveedores

**Tareas**
- Puerto `NewsProviderPort` y los 3 adaptadores.
- Normalización a `RawArticle`, caché, contador de créditos y presupuesto.
- Pruebas con fixtures.
- Script CLI `scripts/probar_proveedor.py` que ejecuta **una** consulta real con confirmación previa y guarda la respuesta como fixture.

**Criterios de aceptación**
- Pruebas sin red pasan.
- Una consulta real por proveedor, aprobada por Benji, devuelve resultados normalizados.
- Se muestran 5 ejemplos reales.

### F4 — Pipeline, LLM y geolocalización

**Tareas**
- Etapas 1–8 de la sección 9 en Celery.
- Adaptador de LLM con prompt versionado.
- Resolutor geográfico con los casos de la sección 11.
- Tabla `processing_errors`.

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

---

## 19. Riesgos y preguntas abiertas

| Tema | Riesgo o pregunta | Mitigación |
|---|---|---|
| Entorno | ¿Desarrollo en Windows (VM 103) o en una VM Linux dedicada? Docker en Windows dentro de una VM requiere virtualización anidada. | Recomendado: VM Linux dedicada en Proxmox. Se decide en F0. |
| Costos | Consumo de créditos de SearchApi y Gemini. | Estimación previa, presupuesto por búsqueda, caché, bitácora de créditos. |
| Calidad geográfica | Las notas rara vez mencionan colonias; muchas solo dicen el estado. | La precisión es explícita y visible; nunca se finge más detalle del que hay. |
| Proveedores | Cambios de API o precio. | Puertos y adaptadores; tres fuentes independientes. |
| Derechos de autor | Contenido de los medios. | Solo metadatos, resumen propio y link; el texto completo no se expone. |
| Integración | Autenticación del sistema principal. | La API queda versionada; la autenticación se diseña en F8. |
