# Historial de cambios

Todos los cambios importantes de este proyecto se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [versionado semántico](https://semver.org/lang/es/): cada fase N cierra con la versión `v0.N.0`.

## [Sin publicar]

### Agregado

- **Fase 3 — Proveedores e ingesta** (en curso).
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
  - ADR-0010 a ADR-0013.

### Cambiado

- Especificación v1.8: F3 pasa a ser "Proveedores e ingesta".
- `PlannedQuery` lleva exclusiones y lugar por separado, y `PlaceFacts`/`QueryPlace` la clave INEGI del estado.
- "Probar concepto" muestra también la consulta del índice local, escrita en palabras.
- El worker y el reloj de Celery escriben logs JSON, igual que la API.

### Corregido

- GDELT repetía la misma ubicación por cada mención; ahora se guarda una vez.

### Desactivado

- Google News RSS fuera de producción por sus términos de uso (ADR-0011, `NEWS_RSS_ENABLED=false`).
- API DOC de GDELT apagada mientras responda 429 (ADR-0012, `GDELT_ENABLED=false`); sus archivos sí se usan en el índice local.
- RSS de medios apagados hasta revisar sus términos (`MEDIA_RSS_ENABLED=false`).

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
