# ADR-0002 — PostgreSQL + PostGIS como única base de datos y catálogo `regions` con claves INEGI

- **Estado:** aceptado
- **Fecha:** 2026-10-15
- **Fase:** F0

## Contexto

El sistema necesita responder preguntas espaciales ("¿esta noticia cae en este municipio?", "¿qué región hay en este punto del mapa?"), buscar nombres de lugares con tolerancia a errores y acentos ("izta" → Iztapalapa) y guardar búsquedas, noticias y auditoría.
El sistema principal al que se integrará este módulo ya usa PostgreSQL.

Los datos geográficos de México vienen del Marco Geoestadístico de INEGI, cuyas claves (CVEGEO) son jerárquicas: estado `09`, municipio `09007`, localidad `090070001`.

## Decisión

1. **Una sola base de datos: PostgreSQL 16 con las extensiones PostGIS, `pg_trgm` y `unaccent`.**
   - PostGIS: geometrías, índices espaciales y consultas como `ST_Contains`.
   - `pg_trgm`: búsqueda difusa de nombres por similitud de trigramas.
   - `unaccent`: comparación sin acentos.
2. **Un catálogo `regions` unificado** para todos los niveles (`country`, `state`, `municipality`, `locality`), con `parent_id` y el código INEGI en `code`.
3. **La jerarquía se resuelve por prefijo de código:** "¿`09007` está dentro de `09`?" es `code LIKE '09%'`, con índice `text_pattern_ops`, sin cálculo geométrico.
4. Para países fuera de México se usa el código ISO-A3 (`COL`).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Una tabla por nivel (`states`, `municipalities`, `localities`) | Duplica lógica de búsqueda y de resolución geográfica; complica "buscar en cualquier nivel". |
| Base de datos de documentos + servicio de geocodificación externo | Agrega dependencias y costos; pierde consultas espaciales locales y la integración con el sistema principal. |
| Búsqueda de texto en un motor aparte (Elasticsearch) | Excesivo para el volumen esperado; `pg_trgm` cubre la búsqueda difusa de nombres. |
| SQLite + SpatiaLite | No soporta bien concurrencia de API + worker ni la escala de geometrías INEGI a resolución completa. |

## Consecuencias

- Las consultas de pertenencia a región son baratas (prefijo de texto) y las espaciales se reservan para "región en un punto".
- El nombre original se guarda intacto (`name`) y se compara con una columna normalizada (`name_norm`: mayúsculas, sin acentos, conservando la Ñ).
- Las geometrías completas viven en PostGIS para cálculos; al navegador llegan simplificadas por PMTiles (ADR-0004).
- Requiere PostgreSQL 16 con PostGIS; en desarrollo se instala del repositorio oficial de PostgreSQL (ADR-0006).
