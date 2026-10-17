# API REST del monitor de noticias (`/api/v1`)

Guía para usar la API desde la pantalla, desde el sistema mayor o desde la terminal. Todas las respuestas de ejemplo son **reales**: salen de la API local del 17/10/2026, con la búsqueda real "Extorsión · Jalisco · últimos 7 días". Las listas largas se recortaron con `…` para que se lean.

- **Documentación interactiva:** <http://localhost:8080/api/v1/docs>. Ahí se ven todas las rutas, sus parámetros y sus errores posibles, y se pueden probar.
- **Dónde correr los ejemplos:** en Ubuntu (WSL). Desde PowerShell, entra primero con `wsl`.
- **Usuario:** hasta la Fase 8 todas las peticiones son del usuario de desarrollo (`DEV_USER`).

## Reglas comunes

**Errores.** Siempre tienen la misma forma, con el mensaje en español y un `code` estable para que otros sistemas reaccionen sin leer el texto:

```json
{ "error": { "code": "search_not_found", "message": "No existe esa búsqueda.", "details": { "id": "…" } } }
```

| HTTP | Cuándo | Ejemplos de `code` |
|---|---|---|
| 404 | Lo pedido no existe | `search_not_found`, `article_not_found`, `concept_not_found`, `region_not_found` |
| 409 | Choca con algo que ya existe o con un tope | `credit_limit_reached`, `concept_name_taken` |
| 422 | Parámetros inválidos | `invalid_request`, `query_budget_exceeded` |
| 500 | Falla inesperada (el detalle queda en el registro, nunca en la respuesta) | `internal_error` |
| 503 | Falta configurar el sistema | `llm_not_configured`, `service_unavailable` |

**Paginación por cursor.** Las listas devuelven `items` y `next_cursor`. Para la siguiente página manda `?cursor=<next_cursor>`. Cuando `next_cursor` es `null`, ya no hay más. Nunca se usan números de página (CLAUDE.md §6.3).

**Fechas.** Se guardan en UTC y se entregan con su zona horaria (`-06:00` = Ciudad de México).

## Flujo de una búsqueda

1. `POST /searches/estimate`: muestra cuánto costaría. **No gasta.**
2. `POST /searches`: la lanza (`202`). **Gasta** créditos de SearchApi y tokens de la IA.
3. `GET /searches/{id}`: su avance (consúltala cada 2 s hasta que `status` sea `completed`, `partial` o `failed`).
4. `GET /searches/{id}/articles`: las notas, y `GET /searches/{id}/aggregates`: el mapa de calor.
5. `GET /articles/{id}`: el detalle de una nota.

## Estimar una búsqueda (no gasta)

`POST /searches/estimate`. El cuerpo es el mismo que el de `POST /searches`:

| Campo | Qué es |
|---|---|
| `concept_ids` | Conceptos (al menos uno, activos, sin repetir) |
| `region_id` | Región (de `/regions`) |
| `days` | Últimos N días (1 a 90; por defecto 7) |
| `date_from` y `date_to` | Rango fijo, en lugar de `days`; deben ir los dos |

```bash
curl -s -X POST http://localhost:8080/api/v1/searches/estimate -H 'Content-Type: application/json' -d '{"concept_ids":[3],"region_id":272,"days":7}'
```

```json
{
  "concepts": [{ "id": 3, "name": "Extorsión" }],
  "region_id": 272,
  "region": "México › Jalisco",
  "date_from": "2026-10-10",
  "date_to": "2026-10-17",
  "queries": [
    {
      "provider": "searchapi",
      "provider_label": "SearchApi (Google News)",
      "text": "(extorsión OR extorsionador OR \"cobro de piso\" OR \"derecho de piso\" OR \"extorsión telefónica\" OR montadeudas) Jalisco -simulacro",
      "keywords": ["extorsión", "extorsionador", "…"],
      "filters": { "country": "México", "language": "español", "period": "últimos 7 días" },
      "estimated_credits": 1
    },
    { "provider": "indice_local", "provider_label": "Índice local (GDELT + medios)", "…": "…", "estimated_credits": 0 }
  ],
  "credits": 1,
  "credits_month": 2,
  "credits_limit": 100,
  "over_limit": false,
  "llm": { "provider": "openai", "model": "gpt-6-luna", "configured": true, "max_articles": 150, "max_cost_usd": 0.0525 }
}
```

`max_cost_usd` es el máximo: las notas ya procesadas en búsquedas anteriores no se vuelven a pagar.

## Lanzar una búsqueda (gasta)

`POST /searches` con el mismo cuerpo. Responde `202` y la manda al worker.

```bash
curl -s -X POST http://localhost:8080/api/v1/searches -H 'Content-Type: application/json' -d '{"concept_ids":[3],"region_id":272,"days":7}'
```

Respuesta (forma; este ejemplo no se ejecutó para no gastar):

```json
{ "search_id": "…", "status": "pending", "estimate": { "…": "lo mismo que /estimate" } }
```

Antes de crear nada revisa que se pueda correr. Si algo falla, **no se crea la búsqueda ni se gasta**:

- `409 credit_limit_reached`: pasaría el tope mensual de créditos;
- `503 llm_not_configured`: falta la llave de la IA en `.env`;
- `422`: los datos no son válidos. Ejemplo real, con solo una de las dos fechas:

```bash
curl -s -X POST http://localhost:8080/api/v1/searches -H 'Content-Type: application/json' -d '{"concept_ids":[3],"region_id":272,"date_from":"2026-10-01"}'
```

```json
{ "error": { "code": "invalid_request", "message": "Para un rango fijo manda date_from y date_to.", "details": {} } }
```

## Estado y avance de una búsqueda

`GET /searches/{id}`. Mientras corre, `progress.stage` dice en qué etapa va (`query`, `dedupe`, `extract`, `enrich`, `geocode`, `filter`, `close`) y los conteos crecen.

```bash
curl -s http://localhost:8080/api/v1/searches/b01afb0d-e78b-4257-8a14-5d2e98082d83
```

```json
{
  "search_id": "b01afb0d-e78b-4257-8a14-5d2e98082d83",
  "status": "completed",
  "region_id": 272,
  "region_code": "14",
  "region_name": "Jalisco",
  "date_from": "2026-10-10",
  "date_to": "2026-10-17",
  "concepts": [{ "id": 3, "name": "Extorsión" }],
  "progress": {
    "stage": "close",
    "articles": 18, "reused": 0, "enriched": 18, "fallback": 5, "skipped_by_cap": 0,
    "in_region": 9, "out_of_region": 7, "unlocated": 2,
    "stages": { "query": { "total": 2, "failed": 0 }, "enrich": { "total": 18, "failed": 0 }, "…": "…" }
  },
  "queries_planned": 2,
  "credits_estimated": 1,
  "credits_used": 1,
  "llm_tokens_in": 52094,
  "llm_tokens_out": 15516,
  "llm_cost_usd": 0.0129,
  "results_count": 18,
  "error_summary": null,
  "created_at": "2026-10-17T09:00:48.189169-06:00",
  "started_at": "2026-10-17T09:00:48.369499-06:00",
  "finished_at": "2026-10-17T09:01:49.588868-06:00"
}
```

`fallback` cuenta las notas que se procesaron solo con título y fragmento, porque el medio no dejó leer el texto. `llm_cost_usd` incluye lo gastado al reprocesar con `make reubicar --con-ia`.

## Historial

`GET /searches?limit=20&cursor=…`: las búsquedas de la persona, de la más reciente a la más vieja.

```bash
curl -s 'http://localhost:8080/api/v1/searches?limit=1'
```

```json
{ "items": [{ "search_id": "b01afb0d-…", "status": "completed", "…": "igual que GET /searches/{id}" }], "next_cursor": null }
```

## Notas de una búsqueda

`GET /searches/{id}/articles`. Van de la más reciente a la más vieja (las que no tienen fecha, al final).

| Parámetro | Qué hace |
|---|---|
| `relevant` | `true` (por defecto): solo las relevantes para algún concepto; `all`: todas |
| `in_region` | `true`: dentro de la región; `false`: fuera; `none`: sin ubicación |
| `precision` | `country`, `state`, `municipality`, `locality` o `unknown` (sin ubicación); se puede repetir |
| `concept_id` | Solo las de ese concepto |
| `limit` y `cursor` | Página (1 a 200, por defecto 50) |

```bash
curl -s 'http://localhost:8080/api/v1/searches/b01afb0d-e78b-4257-8a14-5d2e98082d83/articles?limit=1'
```

```json
{
  "items": [
    {
      "article_id": 11,
      "title": "Morelos en llamas y Sheinbaum pide \"un mes para consulta\", escribe Salvador García Soto",
      "source_name": null,
      "source_domain": "eluniversal.com.mx",
      "url": "https://eluniversal.com.mx/opinion/salvador-garcia-soto/morelos-en-llamas-y-sheinbaum-pide-un-mes-para-consulta",
      "published_at": "2026-10-17T06:32:00-06:00",
      "summary": "La columna describe una crisis de inseguridad en Morelos y cuestiona la respuesta de los gobiernos estatal y federal. Señala aumentos en las denuncias por extorsión, además de homicidios, secuestros y robos, y menciona municipios con altos índices de violencia.",
      "event_type": "extorsión",
      "event_date": null,
      "extraction_status": "ok",
      "enrichment_status": "ok",
      "concepts": [
        {
          "concept_id": 3,
          "name": "Extorsión",
          "is_relevant": true,
          "relevance_score": 1.0,
          "relevance_reason": "La nota aborda el aumento de las denuncias por extorsión en Morelos y menciona expresamente el cobro de piso como práctica criminal."
        }
      ],
      "primary_location": {
        "mention": "Morelos",
        "role": "event",
        "precision": "state",
        "confidence": 0.95,
        "is_primary": true,
        "region_id": 275,
        "region_code": "17",
        "place": "Morelos",
        "lon": -99.10181651110256,
        "lat": 18.732125509858896
      },
      "in_region": false,
      "providers": ["indice_local"]
    }
  ],
  "next_cursor": "WyJ0IiwgIjIwMjYtMTAtMTdUMDY6MzI6MDAtMDY6MDAiLCAiMTEiXQ"
}
```

- `summary` lo escribe la IA: nunca se entrega el texto del artículo (CLAUDE.md §8). Para leerlo completo está `url`.
- El punto (`lon` y `lat`) sale del catálogo INEGI, nunca de la IA.
- `primary_location` en `null` significa "sin ubicación": no se pinta en el mapa.

Solo las de fuera de la región:

```bash
curl -s 'http://localhost:8080/api/v1/searches/b01afb0d-e78b-4257-8a14-5d2e98082d83/articles?in_region=false'
```

Ejemplo de error real, con una precisión que no existe:

```bash
curl -s 'http://localhost:8080/api/v1/searches/b01afb0d-e78b-4257-8a14-5d2e98082d83/articles?precision=colonia'
```

```json
{ "error": { "code": "invalid_request", "message": "Precisión desconocida: colonia.", "details": { "validas": ["country", "locality", "municipality", "state", "unknown"] } } }
```

## Mapa de calor

`GET /searches/{id}/aggregates?level=state|municipality|country`. Cada nota cuenta una vez, en su ubicación principal. Acepta `relevant` igual que la lista de notas.

```bash
curl -s 'http://localhost:8080/api/v1/searches/b01afb0d-e78b-4257-8a14-5d2e98082d83/aggregates?level=state'
```

```json
{
  "level": "state",
  "items": [
    { "region_id": 272, "code": "14", "name": "Jalisco", "count": 7, "lon": -103.21734934861192, "lat": 20.838057309584556 },
    { "region_id": 278, "code": "20", "name": "Oaxaca", "count": 3, "lon": -96.28342500924623, "lat": 17.16368662531788 },
    "…"
  ],
  "coarser": 0,
  "abroad": 0,
  "unlocated": 2,
  "total": 14
}
```

Por municipio (`level=municipality`), la nota de Morelos, que solo tiene estado, **no se reparte entre municipios**: se cuenta en `coarser`.

```json
{
  "level": "municipality",
  "items": [
    { "region_id": 1084, "code": "14039", "name": "Guadalajara", "count": 6, "lon": -103.33579447868962, "lat": 20.678216723435334 },
    { "region_id": 1177, "code": "20043", "name": "Heroica Ciudad de Juchitán de Zaragoza", "count": 3, "lon": -94.91189382153306, "lat": 16.413312053982743 },
    "…"
  ],
  "coarser": 1,
  "abroad": 0,
  "unlocated": 2,
  "total": 14
}
```

`abroad` cuenta las notas de otro país; aparecen con `level=country`.

## Detalle de una nota

`GET /articles/{id}`: lo mismo que en la lista, más todas sus menciones de lugar, el modelo de IA y la versión del prompt.

```bash
curl -s http://localhost:8080/api/v1/articles/11
```

```json
{
  "article_id": 11,
  "title": "Morelos en llamas y Sheinbaum pide \"un mes para consulta\", escribe Salvador García Soto",
  "…": "igual que en la lista",
  "locations": [
    { "mention": "Morelos", "role": "event", "precision": "state", "confidence": 0.95, "is_primary": true, "region_code": "17", "place": "Morelos", "…": "…" },
    { "mention": "Cuernavaca", "role": "mentioned", "precision": "municipality", "confidence": 0.95, "is_primary": false, "region_code": "17007", "place": "Municipio Cuernavaca", "…": "…" },
    "…"
  ],
  "first_seen_at": "2026-10-17T09:00:50.610884-06:00",
  "llm_model": "gpt-6-luna",
  "prompt_version": "enrich_v1"
}
```

`role` es `event` donde pasó el hecho y `mentioned` cuando el lugar solo se nombra.

Una búsqueda o nota que no existe responde `404`:

```bash
curl -s http://localhost:8080/api/v1/searches/00000000-0000-0000-0000-000000000000
```

```json
{ "error": { "code": "search_not_found", "message": "No existe esa búsqueda.", "details": { "id": "00000000-0000-0000-0000-000000000000" } } }
```

## Otras rutas

- **`/health`:** estado de la API, la base, Redis y el worker.
- **`/regions`:** catálogo geográfico, búsqueda por nombre y región en un punto.
- **`/concepts`:** alta, edición, borrado y prueba de conceptos. Un concepto que ya se usó en una búsqueda solo se desactiva.
- **`/local-index`:** vista temporal hasta F6.

Todas están en la documentación interactiva. Los reportes (`/searches/{id}/report`) llegan en la Fase 7.
