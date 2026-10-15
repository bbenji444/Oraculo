# ADR-0003 — Estrategia multiproveedor de noticias

- **Estado:** aceptado
- **Fecha:** 2026-10-15
- **Fase:** F0

## Contexto

El sistema necesita encontrar noticias recientes en español sobre conceptos y regiones de México.
La fuente natural serían los resultados de Google, pero la **Custom Search JSON API de Google está cerrada a clientes nuevos** y los clientes existentes tienen hasta el **1 de enero de 2027** para migrar a otra solución, fecha en que se descontinúa el servicio ([documentación oficial](https://developers.google.com/custom-search/v1/overview), consultada el 15 de octubre de 2026).

Ninguna fuente sola cubre todo: unas son de pago, otras gratuitas pero sin garantía, y cada una tiene cobertura distinta.

## Decisión

Usar **tres proveedores independientes** detrás del puerto `NewsProviderPort`, normalizando todo a un contrato común `RawArticle`:

| Proveedor | Rol | Costo |
|---|---|---|
| **SearchApi**, motor `google_news` ([documentación](https://www.searchapi.io/docs/google-news)) | Principal: resultados reales de Google News. Admite filtros de país (`gl`), idioma (`hl`, `lr`) y tiempo (`time_period`). | De pago por búsqueda |
| **GDELT DOC 2.0** ([documentación](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)) | Volumen y cobertura amplia; filtros `sourcelang` y `sourcecountry`; ventana de 3 meses. | Gratis |
| **Google News RSS** | Respaldo gratuito. | Gratis, sin garantía de servicio |

Reglas comunes:
- Si un proveedor falla, la búsqueda continúa y queda en estado `partial`.
- Cada consulta se registra con su costo en créditos; hay presupuesto por búsqueda y caché de consultas idénticas.
- Los detalles exactos de parámetros se verifican contra la documentación vigente al implementar cada adaptador (F3).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Google Custom Search JSON API | Cerrada a clientes nuevos; se descontinúa el 1 de enero de 2027. |
| Vertex AI Search (alternativa sugerida por Google) | Pensada para buscar en hasta 50 dominios propios, no en todas las noticias. |
| Un solo proveedor de pago | Punto único de falla y de costo; sin respaldo si cambia su API o precio. |
| Solo fuentes gratuitas (GDELT + RSS) | Sin garantía de servicio y cobertura menos precisa que Google News. |
| Raspado directo de sitios de medios | Frágil, costoso de mantener y con riesgos legales y de términos de uso. |

## Consecuencias

- Hay que deduplicar: una noticia puede llegar por varios proveedores (sección 9 de la especificación).
- Los links de Google News RSS vienen codificados y su resolución a la URL del medio no está garantizada (ver especificación, sección 8).
- Agregar o quitar un proveedor no toca la lógica de negocio, solo su adaptador.
- Se necesita llevar cuenta de créditos y una estimación previa visible para el usuario.
