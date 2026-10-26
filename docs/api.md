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
| 403 | Tu rol no permite la acción (por ejemplo, un lector que edita un caso) | `case_forbidden` |
| 404 | Lo pedido no existe (o es un caso del que no eres miembro) | `search_not_found`, `article_not_found`, `concept_not_found`, `region_not_found`, `case_not_found` |
| 409 | Choca con algo que ya existe, con un tope, con una búsqueda que aún corre o con un caso cerrado | `credit_limit_reached`, `concept_name_taken`, `search_not_finished`, `case_closed` |
| 422 | Parámetros inválidos | `invalid_request`, `query_budget_exceeded`, `invalid_case` |
| 500 | Falla inesperada (el detalle queda en el registro, nunca en la respuesta) | `internal_error` |
| 503 | Falta configurar el sistema | `llm_not_configured`, `service_unavailable` |

**Paginación por cursor.** Las listas devuelven `items` y `next_cursor`. Para la siguiente página manda `?cursor=<next_cursor>`. Cuando `next_cursor` es `null`, ya no hay más. Nunca se usan números de página (CLAUDE.md §6.3).

**Fechas.** Se guardan en UTC y se entregan con su zona horaria (`-06:00` = Ciudad de México).

## Flujo de una búsqueda

0. `GET /sources`: las fuentes para los switches (cuáles hay, cuáles cuestan, cuáles van encendidas).
1. `POST /searches/estimate`: muestra cuánto costaría. **No gasta.**
2. `POST /searches`: la lanza (`202`). **Gasta** créditos de SearchApi y tokens de la IA.
3. `GET /searches/{id}`: su avance (consúltala cada 2 s hasta que `status` sea `completed`, `partial` o `failed`).
4. `GET /searches/{id}/articles`: las notas, y `GET /searches/{id}/aggregates`: el mapa de calor.
5. `GET /articles/{id}`: el detalle de una nota.
6. `POST /searches/{id}/report` y `GET /searches/{id}/export`: el reporte en PDF o HTML y las notas en CSV o GeoJSON.

## Categorías de noticias

`GET /categories`. El catálogo con que la IA clasifica cada nota por delito (F12.4, ADR-0029), en su orden, con «Otros» (`is_other: true`) al final. `color` y `symbol` vienen en `null` hasta que se definan con datos reales.

```json
{
  "items": [
    { "id": 1, "name": "Narcotráfico y delitos contra la salud", "description": "Producción, transporte o venta de drogas…", "is_other": false, "color": null, "symbol": null },
    { "id": 14, "name": "Otros", "description": "Cualquier tema que no encaje…", "is_other": true, "color": null, "symbol": null }
  ]
}
```

## Fuentes de la búsqueda (switches)

`GET /sources`. Una por fuente, en el orden de pantalla. Las que no están configuradas (`configured: false`) se muestran apagadas y no se pueden encender. `slow: true` = abre un navegador real (BrowserWork, ADR-0028): tarda más y, si pide captcha, esa fuente se omite y la búsqueda queda `partial`. BrowserWork está programado pero **oculto** desde el 25/10/2026 hasta que corrija sus links; mientras tanto no aparece aquí y pedirlo responde `422`.

```json
{
  "items": [
    { "id": "google_news_rss", "label": "Google News RSS", "paid": false, "slow": false, "configured": true, "default_on": true },
    { "id": "indice_local", "label": "Índice local (GDELT + medios)", "paid": false, "slow": false, "configured": true, "default_on": true },
    { "id": "searchapi", "label": "SearchApi (Google News)", "paid": true, "slow": false, "configured": true, "default_on": false }
  ]
}
```

## Estimar una búsqueda (no gasta)

`POST /searches/estimate`. El cuerpo es el mismo que el de `POST /searches`:

| Campo | Qué es |
|---|---|
| `concept_ids` | Conceptos (al menos uno, activos, sin repetir) |
| `region_id` | Región (de `/regions`) |
| `days` | Últimos N días (1 a 90; por defecto 7) |
| `date_from` y `date_to` | Rango fijo, en lugar de `days`; deben ir los dos |
| `providers` | Fuentes encendidas (`id` de `/sources`). Sin mandar, las de por defecto (`MANUAL_DEFAULT_SOURCES`). Una lista vacía o una fuente sin configurar responde `422` (F12.2, ADR-0027) |

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
  "llm": { "provider": "openai", "model": "gpt-6-luna", "configured": true, "max_articles": 150, "max_cost_usd": 0.0525 },
  "providers": ["searchapi", "indice_local"]
}
```

`providers` dice con qué fuentes se buscaría; `GET /searches/{id}` y el historial devuelven el mismo campo con las fuentes con que se hizo (vacío en las búsquedas de antes de F12.2, que usaron todas).

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
      "providers": ["indice_local"],
      "story_id": null,
      "category": { "id": 11, "name": "Extorsión", "color": null, "symbol": null },
      "category_raw": "cobro de piso"
    }
  ],
  "next_cursor": "WyJ0IiwgIjIwMjYtMTAtMTdUMDY6MzI6MDAtMDY6MDAiLCAiMTEiXQ"
}
```

`category` (F12.4, ADR-0029) es el **delito** del que trata la nota, de las categorías de `GET /categories`; `null` si todavía no se clasifica. `category_raw` es la etiqueta libre que propuso la IA. No confundir con `event_type`, que es lo que hizo la autoridad (detención, cateo).

`story_id` (F12.1c, ADR-0026) agrupa las notas del **mismo hecho** publicadas por varios medios: es el id de la primera nota de la historia y es igual en todas sus notas. `null` = la nota está sola. El monitor junta en una tarjeta las notas visibles con el mismo `story_id` («▸ +N medios»).

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

`GET /searches/{id}/aggregates?level=state|municipality|locality|country`. Cada nota cuenta una vez, en su ubicación principal. Acepta `relevant` igual que la lista de notas. `locality` solo cuenta las notas ubicadas en una localidad (lo usan los reportes de un municipio).

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
  "total": 14,
  "by_category": [
    { "category": { "id": 6, "name": "Armas y explosivos", "color": null, "symbol": null }, "count": 5 },
    { "category": null, "count": 2 }
  ]
}
```

`by_category` cuenta las mismas notas por categoría (F12.4), de la que más tiene a la que menos; `category: null` = notas todavía sin clasificar.

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
  "prompt_version": "enrich_v2"
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

## Reporte y datos de una búsqueda

Solo para búsquedas terminadas (`completed`, `partial` o `failed`). Si la búsqueda todavía corre, las dos rutas responden `409` con `code` `search_not_finished`. Cada reporte o exportación queda en la bitácora como `report.generated` (ADR-0018).

**Reporte.** `POST /searches/{id}/report?format=pdf|html`. Lleva:
- portada;
- resumen ejecutivo escrito por la IA a partir de los resúmenes de las notas;
- mapa con las subregiones coloreadas;
- conteo por subregión;
- notas relevantes con su resumen, lugar y link;
- proveedores y créditos.

La **primera vez** le pide el resumen ejecutivo a la IA (en este ejemplo: 1,880 tokens de entrada, 175 de salida, **0.0003 USD**, 0 créditos de SearchApi). Las siguientes lo reutilizan.

```bash
curl -s -X POST -D - -o reporte.pdf \
  'http://localhost:8080/api/v1/searches/b01afb0d-e78b-4257-8a14-5d2e98082d83/report?format=pdf'
```

```text
HTTP/1.1 200 OK
Content-Type: application/pdf
content-disposition: attachment; filename="reporte-extorsion-jalisco-2026-10-17.pdf"
```

Resultado: 5 páginas A4, 79 KB, en 5.7 s la primera vez (con la IA) y 4.4 s las siguientes. Con `format=html` devuelve la misma página para verla o imprimirla desde el navegador (0.8 s).

**Datos.** `GET /searches/{id}/export?format=csv|geojson`, con las notas relevantes. Nunca el texto completo (§8). No gasta nada.

```bash
curl -s -D - -o notas.csv \
  'http://localhost:8080/api/v1/searches/b01afb0d-e78b-4257-8a14-5d2e98082d83/export?format=csv'
```

```text
HTTP/1.1 200 OK
content-type: text/csv; charset=utf-8
content-disposition: attachment; filename="reporte-extorsion-jalisco-2026-10-17.csv"
```

```text
titulo,medio,publicada,lugar,precision,dentro_de_la_region,latitud,longitud,conceptos,resumen_automatico,proveedores,link
"Morelos en llamas y Sheinbaum pide ""un mes para consulta"", escribe Salvador García Soto",eluniversal.com.mx,17/10/2026 06:32,Municipio Cuernavaca,Municipio,no,18.9331479002984,-99.25995256354925,…
```

- **CSV:** va en UTF-8 con BOM, para que Excel muestre la Ñ al abrirlo con doble clic. Las fechas van en hora de la Ciudad de México. Si un título empieza con `=`, `+`, `-` o `@`, se le antepone un apóstrofo para que Excel no lo tome por fórmula.
- **GeoJSON** (`application/geo+json`): un punto por nota ubicada, con las coordenadas en orden `[longitud, latitud]`. En el ejemplo son 12 puntos: las 14 notas menos las 2 sin ubicación. El objeto `busqueda` dice la región, los conceptos y el periodo.

## Casos de investigación

Un caso agrupa las noticias de una investigación (Fase 9). Reglas que aplican a todas las rutas:

- **Acceso por caso.** Cada persona ve solo los casos de los que es miembro (`case_members`). Quien crea un caso queda como dueño (`owner`). Un caso ajeno responde `404` `case_not_found`, igual que uno que no existe, para no revelar que existe.
- **Roles:**
  - `owner` y `editor` cambian el caso;
  - `viewer` solo lo consulta; si intenta cambiarlo, recibe `403` `case_forbidden`.
- **Casos cerrados o archivados:** solo cambian de estado (reabrir, o archivar uno cerrado). Cualquier otro cambio responde `409` `case_closed`.
- **Bitácora.** Todo queda registrado: crear (`case.created`), editar (`case.updated`), cerrar, archivar o reabrir (`case.closed`, `case.archived`, `case.reopened`) y **abrir** el caso (`case.viewed`). La vista se registra una vez por persona cada 5 minutos, para que las recargas de la pantalla no llenen la bitácora.

**Crear.** `POST /cases` con `name` (de 1 a 120 caracteres), `description` (hasta 2,000) y `sensitivity` (`normal`, `restricted` o `confidential`). Ejemplo real del 21/10/2026:

```bash
curl -s -X POST http://localhost:8080/api/v1/cases -H 'Content-Type: application/json'   -d '{"name": "Homicidio estilista Polanco", "description": "Asesinato del estilista conocido como Micky Hair en Polanco (septiembre de 2025) y su seguimiento.", "sensitivity": "restricted"}'
```

```json
{
  "id": "2d6f9438-886a-444f-84e9-d47a146903c4",
  "name": "Homicidio estilista Polanco",
  "description": "Asesinato del estilista conocido como Micky Hair en Polanco (septiembre de 2025) y su seguimiento.",
  "status": "open", "status_label": "abierto",
  "sensitivity": "restricted", "sensitivity_label": "reservado",
  "created_by": "desarrollo", "closed_at": null,
  "created_at": "2026-10-21T10:40:42.530224-06:00", "updated_at": "2026-10-21T10:40:42.530224-06:00",
  "article_count": 0, "role": "owner", "has_article": null
}
```

Con datos inválidos responde `422` `invalid_case`, con un problema por campo en `details.problemas`, como los conceptos.

**Listar.** `GET /cases` devuelve mis casos, del cambio más reciente al más viejo, con cursor.
- Sin filtro trae abiertos y cerrados; `?status=archived` trae los archivados.
- Con `?contains_article=<id de nota>`, cada caso dice en `has_article` si ya tiene esa nota. Lo usa el botón "Agregar al caso".

**Abrir.** `GET /cases/{id}` devuelve el caso con el rol de quien lo pide y registra `case.viewed`.

```json
{ "error": { "code": "case_not_found", "message": "No existe el caso o no tienes acceso.", "details": { "id": "00000000-0000-0000-0000-000000000000" } } }
```

**Editar.** `PATCH /cases/{id}` cambia solo los campos enviados. Con `status`:
- `closed` cierra el caso y guarda `closed_at`;
- `archived` lo archiva;
- `open` lo reabre y borra `closed_at`.

Una petición sin cambios no escribe nada.

**Noticias del caso.** Agregarlas o quitarlas exige rol `owner` o `editor` y el caso abierto. Cada cambio queda en la bitácora (`case.article_added`, `case.article_removed`) y sube el caso en la lista.

- `POST /cases/{id}/articles` con `{"article_id": 67}` agrega la nota. Si ya estaba, responde `"added": false` y no repite la bitácora; así un doble clic no duplica nada. Una nota inexistente responde `404` `article_not_found`.
- `DELETE /cases/{id}/articles/{article_id}` la quita del caso (`204`). La noticia sigue en el sistema.
- `GET /cases/{id}/articles` lista las notas con el mismo formato de "Notas de una búsqueda", de la más reciente a la más vieja y con cursor. `in_region` va vacío: un caso no tiene región buscada.

Ejemplo real: la primera nota de la historia H9.1 agregada dos veces.

```bash
curl -s -X POST http://localhost:8080/api/v1/cases/2d6f9438-886a-444f-84e9-d47a146903c4/articles \
  -H 'Content-Type: application/json' -d '{"article_id": 67}'
```

```json
{ "article_id": 67, "added": true }
```

La segunda vez responde `{ "article_id": 67, "added": false }`. La lista del caso, recortada:

```json
{ "items": [ { "article_id": 67, "title": "Micky Hair: Qué se sabe del asesinato de estilista de Micky Hair Salon- Grupo Milenio", "published_at": "2026-10-17T20:46:00-06:00", "primary_location": { "place": "Polanco, Alcaldía Miguel Hidalgo", "precision": "locality", … }, "in_region": null, … } ], "next_cursor": null }
```

**Miembros.** Hasta la Fase 8 no hay usuarios reales: el usuario es un texto, como `created_by`, y no hay pantalla para esto.
- `GET /cases/{id}/members` lista quién tiene acceso, el dueño primero. Cualquier miembro lo puede ver.
- `POST /cases/{id}/members` con `{"user_id": "analista-2", "role": "viewer"}` da acceso o cambia el rol. Solo lo hace el dueño (`403` si no), y responde `"changed": false` si ya tenía ese rol.
- `DELETE /cases/{id}/members/{user_id}` quita el acceso: el caso deja de existir para esa persona.

El caso tiene **un solo dueño**: pedir un segundo dueño, cambiarle el rol o quitarlo responde `409` `case_owner_required`. En la bitácora queda `case.member_added` o `case.member_removed`.

## Entidades de un caso (Fase 9.4)

La IA propone las entidades de cada nota que entra a un caso (ADR-0103). Todo nace sugerido; una persona confirma o descarta.

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/cases/{id}/entities?status=suggested` | Entidades en ese estado (`suggested`, `confirmed`, `discarded`), las de más menciones primero. Cada una trae su estatus legal (y el sugerido), sus alias, su región y sus menciones con la cita (`evidence_span`) y la nota. Incluye `counts` por estado y `analysis`: notas pendientes, en cola, leídas, fallidas, costo gastado y costo estimado de lo pendiente. Cualquier miembro. |
| POST | `/cases/{id}/extract` | «Analizar con IA»: encola las notas pendientes o fallidas. Responde `{queued, estimated_cost_usd}`. Gasta tokens. Editor o dueño, caso abierto. |
| POST | `/entities/{id}/confirm` | Cuerpo `{case_id, legal_status}`. En personas, `legal_status` es obligatorio: `mentioned`, `alleged`, `detained`, `charged`, `victim`, `witness` u `official`; nunca "culpable" (422 `invalid_entity_review`). Firma quién y cuándo y va a la bitácora (`entity.confirmed`). |
| POST | `/entities/{id}/discard` | Cuerpo `{case_id}`. Deja de proponerse sin borrarse (`entity.discarded`). |

Agregar una nota con `POST /cases/{id}/articles` la encola sola. Cada lectura queda en la bitácora como `case.entities_extracted`, con modelo, tokens y costo.

Desde la 9.5, cada mención trae su `id` y su `entity_id` (la entidad dueña), y cada entidad trae `merged`: las que se le unieron, con `{id, label, merged_into}`.

## Duplicados de un caso (Fase 9.5)

El sistema **sugiere** qué entidades del caso podrían ser la misma; solo una persona las une (ADR-0104). Unir no mueve nada: se puede separar después.

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/cases/{id}/merge-suggestions` | Pares del mismo tipo con `reason` (`same_name`, `shared_name` o `similar_name`, con `reason_label`), las dos entidades completas para verlas lado a lado y `keep_id`: cuál se propone que quede (la confirmada; si no, la de más menciones). Cualquier miembro. Mirar nunca fusiona. |
| POST | `/entities/merge` | Cuerpo `{case_id, keep_id, merge_id}`. Responde la que queda con las menciones de las dos. 422 `invalid_entity_merge` si son de tipos distintos, alguna está descartada o ya unida, o quedaría la sugerida en lugar de la confirmada. Bitácora `entity.merged`. |
| POST | `/entities/merge/dismiss` | Cuerpo `{case_id, first_id, second_id}`: «No son la misma». Responde `{dismissed}` (`false` si ya estaba). Bitácora `entity.merge_dismissed`. |
| POST | `/entities/{id}/unmerge` | Cuerpo `{case_id}`. Separa la entidad de aquella a la que se unió (lo que se le había unido a ella se va con ella). Bitácora `entity.unmerged`. |
| POST | `/entities/{id}/split` | Cuerpo `{case_id, mention_ids}`. Pasa esas menciones propias a una sugerencia nueva (para dos homónimos que quedaron juntos); debe quedar al menos una. Responde la nueva. Bitácora `entity.split`. |

Las cuatro escrituras piden editor o dueño con el caso abierto.

## Vínculos de un caso (Fase 9.5)

Solo entre entidades **confirmadas** del caso. «Aparecen juntas» se calcula de las notas que comparten; los demás los dibuja el analista.

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/cases/{id}/relationships?status=suggested` | Vínculos en ese estado, los de más confianza primero, con `counts`. Cada uno trae sus dos entidades (con estatus legal), `type` y `type_label`, `symmetric`, `origin` y `origin_label`, `confidence` y `shared_articles` (la evidencia). Un sugerido por coocurrencia tiene `id` nulo. Cualquier miembro. |
| POST | `/relationships` | Cuerpo `{case_id, entity_a, entity_b, type, custom_label?, notes?}`. `type`: `appears_with`, `same_event`, `family`, `associate`, `employer`, `located_in`, `owns` o `custom` (este con `custom_label`, hasta 80 caracteres). Nace confirmado, origen `human`, confianza 1. En los dirigidos (`employer`, `located_in`, `owns`) `entity_a` es quien «es dueño de»… Si ya existía, se confirma ese. 422 `invalid_relationship` si alguna entidad no está confirmada. Bitácora `relationship.created`. |
| POST | `/relationships/confirm` · `/discard` | Cuerpo `{case_id, entity_a, entity_b, type}` (la llave que trae la lista). 404 `relationship_not_found` si no existe. Bitácora `relationship.confirmed` o `relationship.discarded`. |

Las escrituras piden editor o dueño con el caso abierto.

## Otras rutas

- **`/health`:** estado de la API, la base, Redis y el worker.
- **`/regions`:** catálogo geográfico, búsqueda por nombre y región en un punto. Cada región trae `bbox` (todo su territorio) y `focus_bbox` (su parte principal, sin islas ni territorios lejanos): para encuadrar un mapa se usa `focus_bbox`. Ejemplo, Francia: `bbox` `[-61.8, -21.4, 55.9, 51.1]` (de Guadalupe a Reunión) y `focus_bbox` `[-4.8, 41.4, 9.6, 51.1]`.
- **`/concepts`:** alta, edición, borrado y prueba de conceptos. Un concepto que ya se usó en una búsqueda solo se desactiva.

Las rutas temporales `/local-index/*` se retiraron en la Fase 6: el índice local se consulta como un proveedor más dentro de cada búsqueda.

Todas están en la documentación interactiva.
