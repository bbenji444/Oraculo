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

## Qué hay en la base (Fase 1)

| Tabla | Qué guarda |
|---|---|
| `regions` | Catálogo geográfico: 258 países, 32 estados, 2,478 municipios y 296,850 localidades. |
| `concepts` | Conceptos de búsqueda ("Ciberseguridad", "Secuestro"...) con sus palabras clave, exclusiones y color. `deleted_at` marca los borrados lógicos. |
| `audit_log` | Bitácora de auditoría: quién cambió qué y cuándo (por ahora, crear, editar y borrar conceptos). Solo se agregan filas. |
| `alembic_version` | Versión del esquema (migraciones). Hoy: `0006`. |
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
