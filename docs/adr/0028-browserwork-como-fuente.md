# ADR-0028: BrowserWork como fuente de la búsqueda manual (Bing y Google 2)

- **Estado:** Aceptado
- **Fecha:** 25 de octubre de 2026
- **Fase:** F12.3 (aplica el ADR-0023)
- **Decide:** Benji («Integra ya todo con BrowserWork… mediante switches»), con el dictamen de la Dirección del 24/10/2026 que autoriza BrowserWork como fuente complementaria (ADR-0021)

## Contexto

BrowserWork es el servicio del jefe de Benji en `192.168.0.37:8787`. Su código se leyó por SSH solo para entenderlo, sin cambiar nada (`/opt/BrowserWork`). Abre un Chrome real (Zendriver + Xvfb) y busca en varios motores.

Lo que importa para integrarlo:

- **API asíncrona y sin llave:**
  - `POST /api/search {query, pages, engines}` responde un `id`;
  - `GET /api/search/{id}` dice el estado (`queued`, `running`, `done`, `error`, `awaiting_captcha`);
  - `GET /api/search/{id}/results` devuelve los resultados.
- **Un trabajo a la vez** (`_JOB_LOCK`) para todos sus usuarios, con pausas de 1.5 a 3 s entre páginas.
- **Captcha:** el trabajo espera a que una persona lo resuelva, hasta 600 s. `POST /search/{id}/abort` cancela un trabajo que espera captcha; a uno que corre no lo detiene.
- **Resultados de búsqueda web, sin fecha:** título, URL, sitio, descripción y posición. No todos son noticias (también salen Facebook, gobierno, etc.).
- **Motores que se usan aquí:** `bing` (`bing.com/search?…&mkt=es-MX`) y `google2` (Google web, pasando de página con clic en «Siguiente», lo que reduce captchas). Para Google News ya está el RSS (ADR-0021). Yahoo y DuckDuckGo repiten mucho a Bing y se dejan fuera.

## Decisión

1. **Dos proveedores**, `browserwork_bing` y `browserwork_google2`, con un solo adaptador (`adapters/providers/browserwork.py`) detrás de `NewsProviderPort`. Normaliza a `RawArticle`: el sitio pasa a medio, la descripción a fragmento y no lleva fecha.
2. **Solo por su API HTTP:**
   - la configuración es la dirección (`BROWSERWORK_BASE_URL`); no hay llave, usuario ni credencial SSH;
   - el adaptador solo consulta los trabajos que él mismo crea; nunca lista `/api/searches`, que trae las búsquedas de otras personas;
   - nada se cambia en ese servidor;
   - no se porta su disfraz de navegador: nuestro cliente HTTP se identifica como lo que es.
3. **No colgar la búsqueda:**
   - pregunta el estado cada `BROWSERWORK_POLL_SECONDS` (3 s), con un tope de `BROWSERWORK_TIMEOUT_SECONDS` (240 s, menos que los 600 s del captcha);
   - con captcha, error o tope vencido, la fuente falla (`ProviderUnavailableError`) y la búsqueda queda `partial`, con las demás fuentes;
   - si pide captcha, antes cancela su trabajo para liberar el navegador;
   - pide 1 página por motor (`BROWSERWORK_PAGES`) y una consulta a la vez.
4. **Texto de la consulta:** la sintaxis de Google (`OR`, comillas, `-exclusión`, máximo 32 palabras).
   - Google 2 agrega `after:` / `before:`, que Google web sí respeta, para acotar el periodo.
   - Bing no tiene un operador equivalente: puede traer notas viejas, y la IA marca la fecha del hecho.
5. **Switches:** «Bing (BrowserWork)» y «Google 2 (BrowserWork)», gratis, **apagados por defecto**, con aviso «tarda más» (`Source.slow`). Fuera del perfil automático.
6. **Caché:** los resultados se guardan en la caché de consultas (6 h), como los de SearchApi, para no repetir trabajo en el navegador compartido.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Conectarse por SSH y correr su código | Exigiría la credencial del servidor y tocar el sistema del jefe; la API ya da lo necesario. |
| Copiar su buscador (Zendriver) a este proyecto | Habría que mantener un navegador propio, y el ADR-0023 descarta portar el disfraz. |
| Esperar a que una persona resuelva el captcha | Una búsqueda de las 23:00 o un analista ocupado dejaría colgada la búsqueda hasta 10 min. |
| Encenderlo por defecto o en las corridas automáticas | Es lento y depende de un navegador compartido. Primero se mide en manual. |
| Sumar Yahoo y DuckDuckGo | En su mayoría repiten a Bing; se agregan solo si la medición lo justifica. |

## Consecuencias

- **Nuevas fuentes gratis** de búsqueda web. Una búsqueda con BrowserWork tarda más: de segundos a pocos minutos, más si alguien más lo usa.
- **Notas sin fecha de publicación:** solo se juntan como duplicadas si el título es idéntico (`dedupe`). La línea de tiempo (F12.7) usará la fecha del hecho de la IA y, conviene, la fecha de la página al extraer el texto.
- **Privacidad:** las consultas quedan guardadas en el servidor de BrowserWork. Solo se manda el texto de la búsqueda.
- **Riesgos aceptados por Benji (ADR-0023):** la contraseña de `apis` sigue sin rotar (no se usa aquí), y la API de BrowserWork no tiene llave.
- **Criterio para el perfil automático:** una semana de uso manual sin bloqueos y que aporte notas que el RSS y el índice local no traen. Se decide con otro ADR.
- **`# VERIFICAR` con la primera llamada real** (con permiso de Benji): que Google 2 respete `after:`/`before:` y que la cancelación responda como se leyó en el código.

## Primera medición real (25/10/2026)

Con permiso de Benji: una búsqueda por motor de «Fiscalia General de la Republica», México, últimos 2 días, con 1 página. Respuestas grabadas en `backend/tests/fixtures/providers/browserwork_*_fgr_mexico_2d.json`.

| | Bing | Google 2 |
|---|---|---|
| Tiempo total (crear → resultados) | ~5 s (1.8 s en su navegador) | ~5 s (1.4 s en su navegador) |
| Resultados | 10 | 6 |
| ¿Son noticias? | **No**: los 10 son sitios oficiales (fgr.org.mx, gob.mx, fgjcdmx.gob.mx, fiscalia.com) | Sí: notas recientes (El Economista: vinculación de César Jáuregui; Capital 21; la FGR en Chiapas en X) |
| ¿Links usables? | Sí (páginas de inicio) | **No** |
| Captcha | No | No |

- **`after:`/`before:` en Google 2:** sí acotan el periodo; todo lo que trajo era de las últimas horas. Queda verificado.
- **Bing web no sirve para noticias** con el texto de consulta actual: sin operador de fecha, el buscador prioriza los sitios oficiales del término.
- **Google 2 devuelve links reconstruidos.** Es un error de BrowserWork. En `app/engines.py`, `_prefer_google_url`, cuando Google da su link de redirección (`google.com/url?q=<link real>`), BrowserWork no lee el parámetro `q` y arma la URL con el texto que Google muestra arriba del título. Así, «3 reacciones · hace 6 horas» se vuelve `https://3reacciones/` y la nota de El Economista queda como `https://www.eleconomista.com.mx/Politica`. El link real ya no llega a este sistema, así que no se puede corregir aquí.
- **La cancelación** no se probó: no hubo captcha.
