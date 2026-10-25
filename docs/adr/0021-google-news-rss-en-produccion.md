# ADR-0021 — Google News RSS en producción (sustituye al ADR-0011)

- **Estado:** aceptado
- **Fecha:** 2026-10-24
- **Fase:** transversal (proveedores, F3)
- **Decide:** Dirección de Proyecto / Liderazgo Técnico de Oráculo, con el dictamen «ADR-0011-REV» del 24 de octubre de 2026, dirigido a Benjamín Oviedo
- **Sustituye a:** [ADR-0011](0011-google-news-rss-fuera-de-produccion.md)

## Contexto

El ADR-0011 (16/10/2026) apagó Google News RSS por defecto: el propio feed declara en su `<copyright>` que se ofrece para un lector de noticias personal y no comercial, y que cualquier otro uso está prohibido (respuesta grabada en `backend/tests/fixtures/providers/google_news_rss_cdmx_7d.xml`). La decisión quedó pendiente de una revisión de la Dirección.

El adaptador ya estaba construido y probado (39 y 38 notas reales en F3). Mientras estuvo apagado, los resultados de Google News salían solo de SearchApi, de pago: en una búsqueda real del 24/10/2026, SearchApi aportó 20 notas que el índice local no tenía, por 3 créditos.

## Decisión

1. **Google News RSS se activa por defecto** (`NEWS_RSS_ENABLED=true`), también en producción, por el dictamen de la Dirección del 24/10/2026. El dictamen resuelve textualmente:
   - «Se aprueba formalmente la activación del adaptador de Google News RSS para su funcionamiento en el entorno de producción.»
   - «Queda formalmente sustituida y cerrada la ADR-0011.»
2. **Sigue pudiendo apagarse sin tocar código**, con `NEWS_RSS_ENABLED=false` en `.env`. Apagado, explica cómo encenderlo.
3. **Se quita la advertencia de «solo desarrollo»** que se escribía en el registro cada vez que se armaba con la bandera activa.
4. **El número:** el dictamen pide registrar la decisión como «ADR-0014 (o revisión del ADR-0011)». El 0014 ya era el de los ngramas de GDELT, así que se usa el siguiente libre, 0021, y el ADR-0011 se marca como sustituido.
5. **Riesgo aceptado:** el dictamen es una decisión interna y no cambia los términos del feed. La Dirección asume ese riesgo y queda registrado aquí.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Dejarlo apagado | La Dirección lo aprobó; apagado se paga en SearchApi lo que el RSS da gratis. |
| Usar BrowserWork para Google News | El mismo dictamen autoriza BrowserWork, pero para Google News el RSS da la misma fuente sin abrir un navegador: más rápido, sin captchas y ya probado. BrowserWork queda para otros buscadores (Bing, Yahoo, DuckDuckGo), con su propio plan y ADR. |
| Quitar la bandera | Apagarlo rápido, si Google lo bloquea o cambia, es útil y no cuesta nada. |

## Consecuencias

- **Las búsquedas consultan tres proveedores:** SearchApi, el índice local y Google News RSS. El RSS cuesta 0 créditos; la estimación y la bitácora lo muestran como gratuito.
- **Los links de Google News no se resuelven** (decisión de F3: el truco de decodificarlos dejó de funcionar en 2024). Se guarda el link de Google y el medio sale de `<source>`; estas notas se deduplican por título y fecha (§9).
- **Sin garantía de servicio:** Google puede cambiar o limitar el feed sin aviso. Si falla, la búsqueda queda `partial` y lo dice.
- **Ahorro posible en SearchApi:** queda abierto medir con búsquedas reales cuánto de lo que trae SearchApi ya lo da el RSS, antes de bajar `SEARCHAPI_MAX_PAGES`.
- **BrowserWork:** el dictamen también autoriza su despliegue. Se integra aparte, con su plan, su ADR y sin portar el disfraz de navegador (User-Agent y Client Hints falsos).
