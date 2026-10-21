# ADR-0019: Hasta 3 páginas de SearchApi por consulta, solo mientras vengan llenas

- **Estado:** Aceptado
- **Fecha:** 21 de octubre de 2026
- **Decide:** Benji ("aumenta la paginación de SearchApi a mínimo unas 3, logrando que no gaste tanto crédito")

## Contexto

Cada consulta a SearchApi (`engine=google_news`) traía una sola página: 10 notas. Para investigar, 10 notas por concepto son pocas.

La documentación de SearchApi no tiene ningún parámetro para pedir más resultados por página; solo tiene `page`. El 21/10/2026 se midió con 3 créditos aprobados, usando la consulta "Homicidio · Miguel Hidalgo" del 13 al 20/10/2026:

| Página | Resultados | Nuevos (no repetidos) |
|---|---|---|
| 1 | 10 | 10 |
| 2 | 10 | 10 |
| 3 | 10 | 10 |

- Ninguna respuesta trae el bloque `pagination`, así que no sirve para saber si hay más páginas.
- La cuenta (`GET /api/v1/me`) pasó de 94 a 91 créditos restantes. Cada página es una búsqueda exitosa y cuesta 1 crédito.
- Las respuestas quedaron como fixtures en `backend/tests/fixtures/providers/searchapi_homicidio_pagina_*.json`.

## Decisión

- El adaptador pide hasta `SEARCHAPI_MAX_PAGES` páginas (3 por defecto; máximo permitido 10).
- La página siguiente se pide **solo si la anterior vino llena** (10 resultados). Si viene con menos, ya no hay más y no se gasta otro crédito.
- Las notas repetidas entre páginas se quitan y se numeran en orden (`provider_rank` del 1 al 30).
- **Errores.** Si una página extra falla, se conservan las anteriores. Un error HTTP no se cobra; una respuesta 200 sí, aunque no se pueda leer.
- **Presupuesto.** Antes de consultar se reserva el máximo (3 créditos), para no pasarse del tope mensual. Al terminar se devuelve lo que no se gastó. La bitácora (`provider_queries.cost_credits`) y `searches.credits_used` registran lo gastado de verdad, y `params.pages` dice cuántas páginas se pidieron.
- La estimación muestra el máximo: "2 consultas · hasta 3 créditos".

## Alternativas consideradas

- **Pedir siempre 3 páginas sin revisar.** Gastaría créditos en páginas vacías cuando la búsqueda es muy acotada.
- **Usar `pagination.next` como señal.** No viene en las respuestas reales.
- **Pedir más resultados por página (`num`).** SearchApi no lo ofrece para Google News.

## Consecuencias

- Hasta 30 notas de Google por concepto, en lugar de 10, a cambio de hasta 3 créditos.
- Las páginas 2 y 3 traen más ruido. En la prueba, la palabra "Muertos" del concepto Homicidio atrajo notas del Día de Muertos. La IA las marca como no relevantes y no se muestran por defecto, pero sí cuestan lectura de la IA (~0.0007 USD por nota). Conviene afinar las palabras de exclusión de cada concepto.
- Con el tope mensual de 100 créditos, una búsqueda de 2 conceptos puede gastar hasta 6.
