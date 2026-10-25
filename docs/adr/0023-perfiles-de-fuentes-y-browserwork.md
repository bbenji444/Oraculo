# ADR-0023: Perfiles de fuentes (automático fijo y manual con switches) y conexión con BrowserWork

- **Estado:** Aceptado
- **Fecha:** 24 de octubre de 2026
- **Fase:** F12 (se implementa en F12.2 y F12.3)
- **Decide:** Benji, en la conversación del 24/10/2026 («que nosotros podamos activar y desactivar mediante switches qué queremos buscar en cada búsqueda no automatizada»; «que las búsquedas automáticas entonces sean de esa manera»)

## Contexto

Hoy cada búsqueda consulta los proveedores que estén encendidos en `.env`: SearchApi, el índice local y Google News RSS (ADR-0021). El analista no puede elegir fuentes por búsqueda.

La Fase 12 pide dos cosas:
- **Búsqueda manual:** switches para elegir fuentes, incluido BrowserWork.
- **Corrida automática FGR** (07:00, 15:00 y 23:00, ADR-0022): costo y cobertura constantes entre corridas.

**BrowserWork** es el servicio del jefe de Benji en `192.168.0.37:8787` (FastAPI). Abre un Chrome real (Zendriver + Xvfb) y busca en Google, «Google opción 2», Bing, Yahoo, DuckDuckGo y otros. El dictamen de la Dirección del 24/10/2026 (ADR-0021) lo autoriza como fuente complementaria. Al leer su código (solo lectura, sin tocar el servidor) se encontró:
- **Uso asíncrono:** `POST /api/search` con `query`, `pages` (1–10) y `engines` devuelve un `id`. Luego se consulta `GET /api/search/{id}` y `GET /api/search/{id}/results`. `GET /api/health` responde `{"status":"ok"}`; probado desde la PC de desarrollo el 24/10/2026.
- **No pide llave ni usuario.** Cualquier equipo de la red local puede usarla.
- **Captchas:** si aparece uno, la búsqueda queda en `awaiting_captcha` y espera a que una persona lo resuelva, hasta `CAPTCHA_WAIT_S` (600 s por defecto). «Google opción 2» (`google2`) pasa de página con clic en «Siguiente» dentro de la misma pestaña, lo que reduce los captchas pero no los elimina.
- **Resultados web, no solo noticias:** Google 2 y Bing traen páginas web en general.
- **Historial compartido:** las búsquedas quedan guardadas en ese servidor, y `GET /api/searches` lista también las de otras personas.

## Decisión

1. **Perfil automático, fijo en configuración:** Google News RSS + índice local. Cuesta **0 créditos** y no tiene captchas. Las corridas automáticas no muestran switches. SearchApi y BrowserWork no entran por ahora.
2. **Perfil manual con switches,** uno por fuente disponible:

   | Fuente | Encendida por defecto |
   |---|---|
   | Google News RSS | Sí |
   | Índice local | Sí |
   | SearchApi | Se decide con la medición de F12.2 |
   | BrowserWork → Bing | No |
   | BrowserWork → Google 2 | No |

   La estimación de costo se recalcula con los switches. La búsqueda guarda qué fuentes se usaron, y cada nota muestra de qué fuente vino (ya se guarda en `search_results.provider`).
3. **BrowserWork entra solo por su API HTTP**, como un proveedor más detrás del puerto de noticias (`BrowserWorkProvider`, F12.3). Cada motor es un sub-proveedor. Reglas:
   - Sin llave: la configuración es solo la dirección (`BROWSERWORK_BASE_URL` en `.env`).
   - **Nunca** se usa ni se guarda la contraseña de SSH del usuario `apis`.
   - No se modifica nada en ese servidor.
   - No se porta el disfraz de navegador (User-Agent ni Client Hints falsos).
   - El adaptador solo consulta los `id` de búsquedas que él mismo creó; nunca lista `/api/searches`.
4. **Captchas y lentitud:**
   - El adaptador tiene su propio límite de espera, menor que los 600 s de BrowserWork. Si se vence o la búsqueda queda en `awaiting_captcha`, esa fuente se marca fallida y la búsqueda termina `partial`, con las demás fuentes.
   - Timeout, reintentos con backoff y registro en `provider_queries`, igual que los demás proveedores.
5. **Filtro de resultados web:** como Google 2 y Bing traen páginas que no son noticias, sus resultados pasan por la misma lectura de relevancia de la IA. En F12.3 se mide cuántos son de medios.
6. **Criterio para que BrowserWork entre a la corrida automática:** una semana de mediciones en manual sin bloqueos, y que aporte notas que el RSS y el índice no traen. Se decide con datos, en otro ADR.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| SearchApi en la corrida automática | Usa la misma fuente que el RSS (Google Noticias). Costaría créditos en cada corrida, sobre todo por notas repetidas. |
| BrowserWork en la corrida automática desde el inicio | Un captcha a las 23:00 dejaría la fuente esperando a una persona. Primero hay que medirlo. |
| BrowserWork para Google News | El RSS da la misma fuente sin navegador (ADR-0021). |
| Conectarse por SSH al servidor | No hace falta, y exigiría guardar una credencial del servidor del jefe. |
| Switches también en la corrida automática | Las corridas dejarían de ser comparables entre sí. |

## Consecuencias

- Las corridas automáticas no gastan créditos. Su techo es el del RSS: unas 100 notas por consulta. Si una corrida llega justo a ese techo, se parte en grupos de estados (sigue siendo gratis); se implementa en F12.8.
- **Riesgos aceptados por Benji:**
  - La contraseña del usuario `apis` quedó expuesta en un chat y **no se rota por ahora**. No afecta a esta integración, que no la usa.
  - La API de BrowserWork no tiene llave: depende de que la red local sea de confianza. Es del servidor del jefe y no la cambiamos.
- Las consultas manuales que vayan a BrowserWork quedan guardadas en ese servidor. No se le manda nada que no sea el texto de la búsqueda.
- La medición RSS vs SearchApi de F12.2 gasta unos 3 créditos y se pide aprobación antes.
