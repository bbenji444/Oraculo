# ADR-0007 — MapLibre GL JS v6 en lugar de v5

- **Estado:** aceptado
- **Fecha:** 2026-10-15
- **Fase:** F1
- **Decide:** Benji
- **Modifica:** especificación §5.4 (fila "Globo y mapa") y complementa ADR-0004

## Contexto

La especificación v1.0 fijó MapLibre GL JS **v5** con proyección `globe`.
Al empezar la Fase 1 (15 de octubre de 2026), npm muestra:

- `maplibre-gl` **6.14.0** como versión actual (11 de octubre de 2026).
- La última de la línea 5 es **5.24.0** (23 de abril de 2026); desde entonces solo se publica la línea 6.

Cambios relevantes de la 6.0.0 según su [CHANGELOG](https://github.com/maplibre/maplibre-gl-js/blob/main/CHANGELOG.md):

- Distribución **solo ESM** (`maplibre-gl.mjs`). Se importa con `import * as maplibregl from 'maplibre-gl'` o importaciones con nombre.
- El worker se carga desde una URL real: **ya no se necesita `worker-src blob:`** en la política de seguridad de contenido (CSP).
- Requiere **WebGL2** (WebGL1 eliminado).
- Eventos con clases tipadas, `styleimagemissing` solo notifica y se eliminó el `map.transform` interno.

## Decisión

Usar **MapLibre GL JS 6.x** (versión fijada exacta en `package.json`) con proyección `globe`.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Quedarse en v5.24 | Ya no recibe versiones nuevas; empezar el globo (F6) sobre una línea congelada obligaría a migrar después con más código escrito. |
| Esperar a F6 para decidir | El explorador de geodatos de la Fase 1 ya usa MapLibre; decidir dos veces cuesta más. |

## Consecuencias

- La CSP de nginx (`nginx/encabezados-seguridad.conf`) puede quitar `blob:` de `worker-src` en cuanto se verifique en el navegador.
- Se requiere WebGL2: todos los navegadores de escritorio actuales lo soportan; un equipo muy antiguo sin WebGL2 vería un mensaje en lugar del mapa.
- La documentación y ejemplos de v5 en internet pueden no aplicar tal cual; se sigue la guía oficial de migración de v5 a v6.
