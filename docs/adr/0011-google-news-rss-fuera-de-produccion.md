# ADR-0011 — Google News RSS fuera de producción por sus términos de uso

- **Estado:** aceptado (pendiente de revisión legal por el jefe de Benji)
- **Fecha:** 2026-10-16
- **Fase:** F3
- **Decide:** Benji

## Contexto

La especificación (§8) eligió Google News RSS como proveedor de respaldo gratuito. En la primera consulta real aprobada (16 de octubre de 2026, 11:09 hora de la Ciudad de México), el propio feed respondió con este aviso en su elemento `<copyright>`. La cita es textual y la respuesta completa está grabada byte por byte en `backend/tests/fixtures/providers/google_news_rss_cdmx_7d.xml`:

> Copyright © 2026 Google. All rights reserved. This XML feed is made available solely for the purpose of rendering Google News results within a personal feed reader for personal, non-commercial use. Any other use of the feed is expressly prohibited. By accessing this feed or using these results in any manner whatsoever, you agree to be bound by the foregoing restrictions.

En resumen: el feed solo puede usarse en un lector de noticias **personal y no comercial**; cualquier otro uso está prohibido expresamente. Un sistema institucional de monitoreo no encaja en ese uso.

Técnicamente el proveedor funcionó: 39 y 38 notas reales, con medio y fecha (CHANGELOG, Fase 3).

## Decisión

1. Google News RSS queda **desactivado por defecto**: `NEWS_RSS_ENABLED=false`.
   - Sin habilitarlo, el adaptador responde que no está configurado.
   - Las búsquedas lo saltan y el comando `make probar-proveedor` se niega a consultarlo.
2. Solo puede habilitarse a propósito (`NEWS_RSS_ENABLED=true` en `.env`) en desarrollo. Cada vez que se arma con la bandera activa queda una advertencia en el registro.
3. **Nunca se habilita en producción** mientras la revisión legal no diga lo contrario.
4. Las pruebas automáticas siguen usando solo las respuestas grabadas (`tests/fixtures/providers/`). Nunca salen a internet (CLAUDE.md §7).
5. El adaptador y sus pruebas se conservan: si la revisión legal lo permite, o si Google ofrece un acceso con otros términos, se reactiva sin escribir código.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Mantenerlo activo como decía la especificación | Contradice el aviso del propio feed: riesgo legal para la institución. |
| Borrar el adaptador | Perdería el trabajo y las pruebas si la revisión legal lo permite; desactivarlo cuesta lo mismo y es reversible. |
| Resolver los links y leer las notas por otro medio | No cambia los términos del feed, que prohíben "cualquier otro uso". |

## Consecuencias

- En producción quedan dos proveedores: SearchApi (de pago, resultados de Google News bajo contrato propio) y GDELT (gratuito, no garantizado).
- Si GDELT falla, una búsqueda depende solo de SearchApi. La UI y el reporte deben dejar claro qué proveedores respondieron (§8: búsqueda `partial`).
- La especificación §8 pasa a v1.6 con esta decisión.
- **Pendiente:** el resultado de la revisión legal. Si cambia la decisión, se crea un ADR nuevo que reemplace a este.
