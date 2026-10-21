# Base de datos: cómo consultarla y cómo migrarla

La base es **PostgreSQL 16 con PostGIS**, corriendo en Ubuntu dentro de WSL ([ADR-0006](adr/0006-entorno-desarrollo-sin-docker.md)).
Todo lo de esta guía se probó el 15 de octubre de 2026 con los datos reales de la Fase 1.

## Datos de conexión

| Dato | Valor |
|---|---|
| Servidor | `127.0.0.1` (usa este y no `localhost`: desde Windows, `localhost` puede intentar IPv6 y fallar) |
| Puerto | `5432` |
| Base de datos | `monitor_noticias` (la de pruebas es `monitor_noticias_test`; no la uses para consultar) |
| Usuario | `monitor` |
| Contraseña | La de `POSTGRES_PASSWORD` en tu archivo `.env` |

Los servicios deben estar arriba (`wsl make up`).

## Consultar desde Windows con DBeaver o pgAdmin

1. Instala [DBeaver Community](https://dbeaver.io/download/) o [pgAdmin](https://www.pgadmin.org/download/).
2. Crea una conexión nueva de tipo **PostgreSQL** con los datos de la tabla de arriba.
3. En DBeaver, la primera vez te pedirá descargar el controlador de PostgreSQL: acéptalo.
4. Abre `monitor_noticias` › `Esquemas` › `public` › `Tablas` › `regions`.

DBeaver muestra las columnas `geom` y `centroid` como mapa en la pestaña **Spatial** del visor de datos.

## Consultar desde la terminal

```powershell
wsl make db-shell
```

Abre `psql` ya conectado. Para salir: `\q`.

## Qué hay en la base

| Tabla | Qué guarda |
|---|---|
| `regions` | Catálogo geográfico: 258 países, 32 estados, 2,478 municipios y 296,850 localidades. |
| `concepts` | Conceptos de búsqueda ("Ciberseguridad", "Secuestro"...) con sus palabras clave, exclusiones y color. `deleted_at` marca los borrados lógicos. |
| `audit_log` | Bitácora de auditoría: quién cambió qué y cuándo (conceptos, búsquedas, reportes y, desde la Fase 9, casos y entidades, incluido **ver** un caso). Solo se agregan filas. |
| `provider_queries` | Cada petición a un proveedor de noticias (SearchApi, GDELT, Google News RSS): texto, resultado, si vino de caché y créditos gastados. |
| `news_index` | Índice local de notas que junta la ingesta cada 15 minutos (GDELT por archivos y RSS de medios): título, fragmento, medio, fecha, link y pistas de ubicación de GDELT. Con los ngramas de GDELT (ADR-0014) también `body_terms`: frases del cuerpo normalizadas, **solo para buscar** (nunca se muestran) y borradas a los 30 días. No guarda artículos. |
| `ingest_runs` | Cada corrida de la ingesta: qué archivo o feed se leyó, bytes descargados, notas vistas y guardadas, errores. |
| `searches` | Cada búsqueda (F4): quién, dónde, qué fechas, en qué etapa va (`progress`) y cuánto costó (créditos de SearchApi y tokens de Gemini). |
| `search_concepts` | Los conceptos de cada búsqueda, copiados al momento de buscar para que editarlos no cambie el historial. |
| `articles` | Cada nota una sola vez en todo el sistema (por URL canónica): metadatos, resumen propio de la IA, tipo de evento y estado de extracción y enriquecimiento. No guarda el artículo. |
| `article_texts` | Texto extraído de cada nota, **solo para procesar**: no se expone y se borra a los 30 días (ADR-0015). |
| `article_concepts` | Si una nota es relevante para cada concepto, con su puntaje y la razón. |
| `article_locations` | Cada lugar que menciona una nota, resuelto contra el catálogo INEGI: región, precisión, confianza y si es la ubicación principal. El punto sale del catálogo, nunca de la IA. Guarda también las pistas de la IA (tipo de lugar, estado y país, migración 0014) para volver a ubicar sin pagar (`make reubicar`). |
| `search_results` | Qué notas encontró cada búsqueda, con qué proveedor y en qué posición, y si caen dentro de la región buscada. |
| `processing_errors` | Lo que falló al procesar una nota o una búsqueda (etapa, tipo, mensaje). Un error en una nota no detiene a las demás. |
| `reports` | El resumen ejecutivo de cada búsqueda, escrito una vez por la IA y guardado para no volver a pagarlo (F7, ADR-0018). |
| `places` | ~107 mil colonias y zonas de OpenStreetMap, sacadas del mapa base, para ubicar lo que INEGI no tiene (ADR-0020). |
| `entities` | Tablero de investigación (Fase 9): personas, organizaciones, lugares y vehículos como objetos propios. Las personas llevan estatus legal (lo que dice la nota, nunca "culpable"); todo nace `suggested` y solo una persona lo confirma o descarta, con su nombre y la hora (ADR-0101, 0104, 0105). Los lugares se ligan a `regions` o `places`. |
| `entity_aliases` | Otros nombres de cada entidad ("Eduardo N", "Micky Hair"). |
| `entity_mentions` | La evidencia: en qué nota aparece cada entidad, con su rol, su confianza y una cita corta (máximo 300 caracteres) que sobrevive al borrado del texto de la nota. |
| `relationships` | Vínculos entre dos entidades (aparecen juntas, mismo hecho, familiar…), con su origen (coocurrencia, IA o humano), confianza y revisión. |
| `external_links` | **Reservada y vacía** (ADR-0101): enchufe futuro hacia registros de otras bases del sistema Oráculo. Ninguna lógica de la Fase 9 la usa; una prueba lo vigila. |
| `cases` | Casos de investigación (Fase 9): nombre, estado (abierto, cerrado, archivado) y sensibilidad (normal, reservado, confidencial). La fecha de cierre va con el estado. |
| `case_members` | Quién puede ver o editar cada caso (dueño, editor, lector). Un solo dueño. Hasta la Fase 8, el usuario es el de desarrollo. |
| `case_articles` | Noticias que forman parte de cada caso. Borrar el caso no borra la noticia. Desde la 9.4, `entities_status` dice si la IA ya leyó la nota (`pending`, `queued`, `done`, `failed`, `skipped`) y `entities_cost_usd` cuánto pagó ESTE caso por ella (0 si se reutilizó). |
| `entity_extractions` | Lo que respondió la IA de cada nota al proponer entidades (Fase 9.4, ADR-0103): las propuestas que pasaron la revisión contra el texto y las descartadas con su motivo, modelo, tokens y costo. Una por nota y versión de prompt: si la nota entra a otro caso se reutiliza sin volver a pagar. |
| `case_entities` | Entidades de cada caso, con su rol, su estado en ESE caso (en el caso, línea de investigación, descartada) y una etiqueta del analista. |
| `case_notes` | Notas del investigador, ancladas a lo más a una entidad, noticia o vínculo. |
| `alembic_version` | Versión del esquema (migraciones). Hoy: `0020`. |
| `spatial_ref_sys` | Tabla interna de PostGIS (sistemas de coordenadas). No se toca. |

Columnas principales de `regions`:

| Columna | Ejemplo | Para qué |
|---|---|---|
| `code` | `09007` | Clave INEGI (municipio = estado + municipio) o código ISO del país (`COL`). |
| `level` | `municipality` | `country`, `state`, `municipality` o `locality`. |
| `name` | `Iztapalapa` | Nombre original, con acentos. |
| `name_norm` | `IZTAPALAPA` | Nombre para comparar: mayúsculas, sin acentos, **con Ñ**. |
| `display_prefix` | `Alcaldía` | Para mostrar "Alcaldía Iztapalapa". |
| `parent_id` | (id de CDMX) | Región que la contiene. |
| `aliases` | `{CDMX,DF}` | Otros nombres con que se reconoce el lugar en una nota (lista curada en `geodata/aliases.csv`). |
| `search_terms` | `{"Ciudad de México",CDMX}` | Con qué palabras se busca el lugar en los proveedores de noticias; vacío = se usa `name` (`geodata/search_terms.csv`, ADR-0009). |
| `iso_a2`, `fips_code`, `name_en` | `ES`, `SP`, `Spain` | Solo países: códigos para filtrar por país en cada proveedor (ADR-0009). |
| `geom` | (polígono) | Forma completa. Vacía en localidades rurales que solo tienen punto. |
| `centroid` | (punto) | Punto representativo, siempre dentro de la forma. |
| `bbox` | `{-99.14,19.28,-98.96,19.40}` | Rectángulo [oeste, sur, este, norte]. |

## Consultas útiles

```sql
-- Cuántas regiones hay por nivel
SELECT level, count(*) FROM regions GROUP BY level;

-- Los municipios de un estado (por su clave)
SELECT code, display_prefix, name
FROM regions
WHERE level = 'municipality' AND code LIKE '09%'
ORDER BY name_norm;

-- ¿Qué hay en un punto? (lon, lat) — aquí, el Zócalo
SELECT level, display_prefix, name, code
FROM regions
WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(-99.1332, 19.4326), 4326))
ORDER BY level;

-- Buscar por nombre sin acentos (conserva la Ñ)
SELECT code, display_prefix, name
FROM regions
WHERE name_norm LIKE '%PEÑON%';

-- Las migas de pan de una región: Iztapalapa → CDMX → México
WITH RECURSIVE cadena AS (
    SELECT id, parent_id, name, level FROM regions WHERE code = '09007'
    UNION ALL
    SELECT r.id, r.parent_id, r.name, r.level FROM regions r JOIN cadena c ON r.id = c.parent_id
)
SELECT name, level FROM cadena;

-- Exportar municipios de un estado con su forma como GeoJSON
SELECT code, name, ST_AsGeoJSON(geom) FROM regions
WHERE level = 'municipality' AND code LIKE '10%';

-- Conceptos vigentes (sin los borrados) con cuántas palabras clave tienen
SELECT id, name, is_active, cardinality(keywords) AS palabras, color
FROM concepts
WHERE deleted_at IS NULL
ORDER BY name_norm;

-- Bitácora: los últimos 20 cambios, con qué campos cambiaron
SELECT created_at AT TIME ZONE 'America/Mexico_City' AS cuando, user_id, action,
       entity_id, payload->'changed' AS campos, host(ip) AS ip
FROM audit_log
ORDER BY id DESC
LIMIT 20;

-- Con qué palabras se busca cada lugar (vacío = su nombre oficial)
SELECT code, name, search_terms FROM regions WHERE cardinality(search_terms) > 0;

-- En qué va el análisis de entidades de cada caso y cuánto lleva gastado
SELECT c.name, ca.entities_status, count(*) AS notas, sum(ca.entities_cost_usd) AS usd
FROM case_articles ca JOIN cases c ON c.id = ca.case_id
GROUP BY c.name, ca.entities_status ORDER BY c.name;

-- Lo que la IA propuso y se descartó por no estar en la nota (para medirla)
SELECT article_id, rejected_count, output->'rejected' AS descartadas
FROM entity_extractions WHERE rejected_count > 0 ORDER BY id DESC LIMIT 20;
```

> Consejo: compara siempre con `name_norm` (y escribe la búsqueda en mayúsculas sin acentos), no con `name`. Así "Peñón" y "PEÑON" coinciden, pero "Penon" no.

## Migrar la base a otro servidor

### 1. Respaldar (en esta máquina)

```powershell
wsl make db-dump
```

Crea `backups/monitor_noticias_<fecha>.dump` (≈177 MB con los datos de la Fase 1). La carpeta `backups/` está en `.gitignore`: los respaldos nunca van al repositorio.

El respaldo usa el formato comprimido de `pg_dump` (`-Fc`) y deja fuera dos cosas a propósito:
- los datos de `spatial_ref_sys`: el servidor destino ya los trae al instalar PostGIS, y copiarlos provoca errores al restaurar;
- los comentarios de las extensiones: el usuario de la aplicación no puede recrearlos.

### 2. Preparar el servidor destino

Requisitos: **PostgreSQL 16 o más reciente** con **PostGIS 3.x**. Como superusuario (`postgres`):

```sql
CREATE ROLE monitor LOGIN PASSWORD 'una-contraseña-segura';
CREATE DATABASE monitor_noticias OWNER monitor;
\c monitor_noticias
CREATE EXTENSION postgis;
CREATE EXTENSION pg_trgm;
CREATE EXTENSION unaccent;
```

PostGIS solo lo puede instalar un superusuario; por eso va antes de restaurar.

### 3. Restaurar

Copia el archivo `.dump` al servidor y corre:

```bash
pg_restore --no-owner -h <servidor> -U monitor -d monitor_noticias monitor_noticias_<fecha>.dump
```

### 4. Verificar

```sql
SELECT level, count(*) FROM regions GROUP BY level;     -- 258 / 32 / 2478 / 296850
SELECT version_num FROM alembic_version;                -- 0003
SELECT string_agg(name, ' › ' ORDER BY level) FROM regions
WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(-99.1332, 19.4326), 4326));
-- México › Ciudad de México › Cuauhtémoc › Cuauhtémoc
```

**Prueba real del 15 de octubre de 2026:** se restauró el respaldo en una base nueva en 77 s, con **0 errores**. Los conteos y una huella MD5 de claves y nombres por nivel fueron idénticos a la base original.

### 5. Conectar la aplicación al servidor nuevo

Cambia en `.env` las variables `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD` y `POSTGRES_DB`, y reinicia con `wsl make down` y `wsl make up`. El código no cambia: solo lee esas variables.

## Si cambias el esquema

Los cambios de estructura (tablas, columnas, índices) **solo** se hacen con migraciones de Alembic (CLAUDE.md §6.3), nunca a mano en DBeaver. Si consultas, no hay problema. Si escribes o borras datos a mano, se pueden recuperar recargando los geodatos con `wsl make geo-load`.
