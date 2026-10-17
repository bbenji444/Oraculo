# ADR-0015 — Extracción de texto, su retención y el control de costo de la IA

- **Estado:** aceptado
- **Fecha:** 2026-10-16
- **Fase:** F4
- **Decide:** Benji

## Contexto

La Fase 4 convierte una búsqueda en notas resumidas, clasificadas y ubicadas (especificación §9–§11). Para eso hace dos cosas nuevas que cuestan algo:

- **Leer el texto de cada nota.** El título y el fragmento no bastan para saber dónde pasó algo ni si es relevante. trafilatura (en el stack de §5.4) baja la página del medio y separa el cuerpo de menús y anuncios. Algunos medios lo impiden con muros de pago o bloqueos.
- **Pedirle a Gemini** el resumen, la relevancia por concepto y las menciones de lugar. Gemini cobra por tokens. Precios vigentes al 16/10/2026 para `gemini-2.5-flash` ([página de precios](https://ai.google.dev/gemini-api/docs/pricing)):
  - **Entrada:** 0.30 USD por millón de tokens.
  - **Salida:** 2.50 USD por millón de tokens.
  - **Nivel gratuito:** existe.

## Decisión

1. **El texto extraído es solo para procesar.**
   - Se guarda en `article_texts`, nunca se expone en la API ni en reportes (CLAUDE.md §8) y se borra a los `ARTICLE_TEXT_RETENTION_DAYS` días (30).
   - Lo que se conserva de cada nota es su título, el link, el resumen propio y la ubicación.
2. **Extracción con límites.**
   - Tiempo máximo y concurrencia limitada por búsqueda, con el cliente HTTP compartido (ADR-0010).
   - Si falla, se usa título + fragmento y la nota queda con `extraction_status = fallback`. No se pierde: solo se procesa con menos información.
3. **Control de costo de Gemini.**
   - **Antes de gastar:** se estima el costo (~0.0014 USD por nota con ~2,000 tokens de entrada y ~300 de salida) y se muestra.
   - **Tope:** `LLM_MAX_ARTICLES_PER_SEARCH` (150) notas enriquecidas por búsqueda.
   - **Caché:** por (`text_hash`, `prompt_version`, `concept_ids`), para no volver a pagar una nota ya procesada.
   - **Registro:** se anotan los tokens reales y el costo estimado de cada búsqueda.
4. **La IA nunca da coordenadas.** Solo devuelve menciones de lugar (texto). La ubicación y el punto del mapa salen del catálogo INEGI (§11).

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Enriquecer solo con título y fragmento | Más barato, pero pierde la mayoría de los lugares: las notas rara vez nombran la colonia o el municipio en el título. |
| Guardar el texto completo para siempre | Riesgo de derechos de autor y espacio en disco sin beneficio: el resumen y la ubicación ya quedan guardados. |
| Modelo más barato (`gemini-2.5-flash-lite`, 0.10 / 0.40 USD) | Se puede cambiar con `LLM_MODEL` si la calidad alcanza; se empieza con el de la especificación y se compara con datos reales. |

## Consecuencias

- Una búsqueda de 100 notas cuesta ~0.14 USD de Gemini, más los créditos de SearchApi.
- Las notas de medios con muro de pago se ubican con menos precisión.
- Reprocesar con un prompt nuevo (`enrich_v2`) vuelve a pagar, porque cambia la llave de la caché.
