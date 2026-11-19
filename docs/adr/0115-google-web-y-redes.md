# ADR-0115: Google web y redes sociales, con la plataforma de cada nota

- **Estado:** aceptado (19/11/2026, Benji: «Sí, apruébalos»; propuesto el 18/11/2026).
- **Fase:** F12 (búsqueda «casi tan natural como Google», punto 3, parte del servidor). La pantalla está en el [ADR-0117](0117-plataformas-y-no-relevantes-en-pantalla.md).

## Contexto

Benji (18/11/2026) buscó «Hacker Eternal» en el monitor y en Google. En Google salían publicaciones de Facebook, X, YouTube e Instagram del periodista que destapó el caso; en el monitor, ninguna. Además, las 6 notas correctas que sí llegaron por Google News RSS quedaron como no relevantes: su link es de Google (`news.google.com/rss/articles/…`), no se puede descargar y la IA solo vio título y fragmento.

Ninguna fuente que teníamos trae redes:

- Google News (SearchApi `google_news` y el RSS) solo indexa medios.
- GDELT y el índice local, tampoco.

La búsqueda web normal de Google sí las trae. SearchApi la ofrece con el motor `google`, con la misma llave y la misma cuenta de créditos que ya usamos. A la cuenta le quedan **47 créditos de prueba que no se renuevan**.

Documentación consultada el 18/11/2026: https://www.searchapi.io/docs/google. Se grabó una respuesta real con 1 crédito (`backend/tests/fixtures/providers/searchapi_web_hacker_eternal_7d.json`: «hacker eternal», `gl=mx`, `hl=es`, `nfpr=1`, `time_period=last_week`). Lo que se vio:

- 9 resultados en `organic_results` y 4 en `inline_videos`, más `pagination.next`.
- `source` dice la red y el autor: «Facebook · Ignacio Gómez Villaseñor», «X · ivillasenor», «YouTube · La Saga - US», «Instagram · ivillasenor87». `domain` falta en muchas.
- 7 de los 9 `link` son `https://www.google.com/goto?url=…`: una redirección 302 de Google a la página real.
- `date` viene a veces y en texto («hace 15 horas», «hace 5 días»).
- Los títulos largos vienen cortados con « ...».
- `favicon` e `image` son imágenes en base64 de decenas de KB.

## Decisión

### 1. Una fuente nueva: «Google web» (`searchapi_web`)

- `Provider.SEARCHAPI_WEB = "searchapi_web"`, justo después de `searchapi`. Su dialecto: «Google web», 1 crédito por página, con caché y sin operadores de fecha en el texto (la fecha va como parámetro).
- Adaptador `adapters/providers/searchapi_web.py`, con el mismo `ProviderHttpClient` y los mismos `time_params` que el de Google News.
- Se registra en la fábrica, en el worker, en los switches de fuentes (de pago), en `make probar-proveedor`, en `.env.example` y en la configuración (`SEARCHAPI_WEB_MAX_PAGES=1`).

### 2. Qué se le pide

- `engine=google`, `q`, `hl=es`, `gl=<país en minúsculas>` (en «Mundo», `gl=mx`), `nfpr=1` y el periodo (`time_period` o `time_period_min`/`time_period_max`).
- No se mandan `verbatim`, `link=resolved` ni `num`. `num` y `link` están retirados; con `verbatim`, Google ignora el filtro de tiempo.
- `nfpr=1` es para que Google no corrija el texto: Benji no quiere que «Hacker» se vuelva «Hackeo».
- **Una consulta por concepto** (`literal_only` en el dialecto): la primera palabra clave tal cual, sin comillas ni OR ni exclusiones, más el lugar si la región es un estado o municipio. En un país o en «Mundo», solo el texto. La subdivisión no va en el texto, pero sí filtra lo que llega, como en las demás fuentes.
- Por defecto, 1 página (10 resultados, 1 crédito).
- **En «Mundo» va `gl=mx`**, a diferencia de Google News (ADR-0112). En la búsqueda web `gl` es el país de quien busca: acomoda los resultados, no los filtra. Sin él, SearchApi busca como desde Estados Unidos. Medido el 18/11/2026: «Hacker Eternal» en «Mundo» sin `gl` trajo 2 resultados; con `gl=mx`, 9 páginas y 4 videos, lo que Benji ve en Google desde México.

### 3. Qué se lee

- Se leen estas secciones: `organic_results`, `inline_videos`, `inline_shorts`, `inline_tweets`, `top_stories`, `discussions_and_forums` y `perspectives`.
- Se ignoran anuncios, shopping, mapas, `knowledge_graph`, `related_questions` y `ai_overview`: no son publicaciones, y el resumen de Google no se reproduce (CLAUDE.md §8).
- **Títulos cortados.** Se quita « ...» o «…» y la nota queda marcada (`RawArticle.title_truncated`, que también viaja en la caché).
- **Fechas.** `domain/result_dates.parse_result_date` (dominio puro) entiende:
  - «hace N minutos/horas/días/semanas/meses/años», «hace un día», «hace 1 mes», «ayer» y «hoy»;
  - «N days/weeks/months/years ago» y «21h ago»;
  - «17 nov 2026», «17 de nov. de 2026» y «Nov 30, 2022»;
  - «17 nov» o «Nov 17», sin año: el año en curso, o el anterior si la fecha caería en el futuro (revisión del 18/11/2026).

  Un mes cuenta como 30 días y un año como 365: es una fecha aproximada, como la de Google. Las fechas sin hora quedan a mediodía de la Ciudad de México. Si no entiende el texto, o la fecha cae en el futuro, devuelve `None`: nunca inventa.

- **Links `google.com/goto`.** Se piden a Google con un cliente aparte, sin la llave de SearchApi y **sin seguir la redirección**, y se lee `Location`.
  - Ese cliente espera 5 segundos y hace un solo intento. Los links se piden **uno por uno**.
  - **Si Google no redirige, el resultado se queda con su link de Google** (revisión del 18/11/2026). Pedidos seguidos, Google contesta 200 con su página «Verificando tu solicitud» en lugar del 302: en la búsqueda real de «Hacker Eternal» en Mundo, 8 de 10 resultados se perdían así, casi todos de Facebook, Instagram y YouTube. Esa verificación **no se intenta pasar**: en cuanto aparece, los demás `goto` de la página ya no se le piden a Google y se quedan como vinieron. En el navegador del analista ese link sí abre la publicación.
  - La plataforma de esos resultados sale del nombre que da Google («X · ivillasenor»), porque el dominio es de Google (sección 4).
  - La extracción no descarga un `goto` (`is_google_redirect`, motivo `GOOGLE_LINK_FALLBACK_REASON`): bajaría la verificación de Google, no la nota. Se usan título y fragmento, como con las redes.
  - Un link mal formado, o una redirección que lleva a otra página de Google, se descarta.
  - Los `google.com/url?q=` ya traen el destino y no se piden. Si el `Location` de una redirección es otro `google.com/url?q=`, se lee su destino igual.
  - `resolve` nunca lanza: con un `Location` mal formado, un error de `httpx2` o un `ValueError`, esa nota se queda con su link de Google y la consulta sigue (revisión del 18/11/2026).
- **Sin créditos o llave rechazada** (revisión del 18/11/2026). SearchApi solo documenta que con 0 búsquedas «searches are rejected», sin el código. Se toman 402 y 429 como «sin créditos» (`ProviderNoCreditsError`, `# VERIFICAR` con la cuenta en 0) y 401/403 como llave rechazada (`ProviderAuthError`). Ninguno se reintenta: el cliente de Google web se arma con `no_credit_statuses`. El motor de Google News de SearchApi se deja como estaba.
  - `ExecuteQueries` le pone a esa consulta un aviso (`notice`): «Google web no pudo buscar: sin créditos de SearchApi» o «Google web no pudo buscar: SearchApi rechazó la llave».
  - Si otra fuente sí respondió, esa consulta cuenta como respondida sin notas y la búsqueda **no queda `partial`** por eso: no hay nada que reintentar, y «parcial» haría pensar que faltó algo arreglable. `provider_queries` sí guarda el error real (estado `error`, el código HTTP y el texto de SearchApi), y no se cobra. En `searches.queries_executed` esa consulta aparece como `ok` con 0 notas.
  - Si Google web era la única fuente, la búsqueda falla como siempre, con el aviso.
- **Sin resultados** (revisión del 18/11/2026). Cuando Google no encuentra nada, SearchApi contesta HTTP 200 con `{"error": "Google didn't return any results."}`; su especificación (`openapi/google.yaml`) lo describe como «Error message when the page has no results». Se toma como una página vacía (`NO_RESULTS_ERROR`), no como error: antes la búsqueda quedaba `partial` sin nada que reintentar.
  - Pasó en 3 de 9 búsquedas rápidas reales: «Pillofon Luisito Comunica», «ciberataque en México» y «cateo de la Fiscalía General de la República», con la última semana o el último día. El HTML que guardó SearchApi dice «No se han encontrado resultados para tu búsqueda»: no es un bloqueo. Sin `nfpr=1` da lo mismo (medido).
  - **Sí cobra el crédito**: el saldo bajó de 40 a 31 con 9 consultas, 3 de ellas vacías. Google con filtro de fecha es más estricto que lo que ve el analista en su navegador.
  - El worker deja el aviso en `searches.progress.notice` (`NoticedSearchStore`, que lo pone en cada avance porque `RunSearch` reemplaza el avance completo en cada etapa).

### 4. La plataforma de cada nota (`domain/platforms.py`)

`Platform` es un StrEnum con el contrato de la pantalla: `news`, `facebook`, `x`, `youtube`, `instagram`, `tiktok`, `reddit`, `telegram` y `web`. En español: Noticias, Facebook, X, YouTube, Instagram, TikTok, Reddit, Telegram y Otros sitios.

`platform_of(source_domain, url, providers, source_label)` aplica esta regla, en orden:

1. **Red social por dominio**, el del medio o el del link. Cuenta el dominio exacto o un subdominio suyo: `m.facebook.com` es Facebook, pero `box.com` no es X. Los dominios de Google no dicen nada.
2. **Red social por el nombre que da Google** («Facebook · Autor»), solo si no hay un dominio útil.
3. **Noticia o sitio.** Es `news` si la encontró una fuente de prensa (`searchapi`, `google_news_rss`, `gdelt` o `indice_local`). Si solo la trajo Google web, es `web`.

- La plataforma **se calcula al leer**, sin columna nueva, así que vale también para las notas viejas.
- El medio se guarda limpio, tal como lo da Google («Milenio»); la sección (`top_stories`...) va en `raw["section"]` (revisión del 18/11/2026). Antes se guardaba «Noticias · <medio>» para reconocer las noticias destacadas, pero esa marca salía en el CSV y en los reportes. Una destacada casi siempre la trae también el RSS con el mismo texto y entonces es `news`; la que solo trajo Google web queda en `web` («Otros sitios»), porque la sección no se guarda en la base (sin migración).
- Sale en `ArticleOut.platform` (`docs/api.md`) y en la columna «plataforma» del CSV.

### 5. Pipeline

- **Notas sin fecha.** En una búsqueda **manual**, una nota sin fecha de Google web se queda (`kept_by_window`, dialecto con `trusts_window`): Google ya filtró por periodo. Una sin fecha de otra fuente sigue fuera, como siempre. En las corridas automáticas, nada sin fecha se queda. El filtro por la fecha del hecho que da la IA sigue igual.
- **Las redes no se descargan.** Piden iniciar sesión. Se usan título y fragmento, con el motivo «Publicación de red social: no se descarga…» (`SOCIAL_FALLBACK_REASON`).
- **Duplicados de redes, solo por link.** Las publicaciones de una página repiten título («Ignacio Gómez Villaseñor»), y por título se volverían una sola. `canonical_url` junta los alias de cada red:
  - `m.facebook.com` → `facebook.com`;
  - `twitter.com` → `x.com`;
  - `youtu.be/ID` → `youtube.com/watch?v=ID`, sin `si=` ni `feature=`.
- **Títulos cortados.** Un título cortado de 6 palabras o más es la misma nota que la de título completo si coincide palabra por palabra al inicio, con fechas a ±2 días. La nota que se conserva se queda con el título completo y con la fecha que haya.
- **Fecha y link al juntar** (revisión del 18/11/2026). Al juntar dos copias, la que se conserva toma siempre su fecha o, si no tiene, la de la otra: una nota de Google web sin fecha toma la del RSS o del índice local, y se queda con su link real.
- **La misma publicación por RSS y por Google web.** El RSS da Facebook o X con `source_domain` de la red y el link de Google News; Google web da el link real. Se juntan solo si las dos son de la misma red (`m.facebook.com` cuenta como `facebook.com`), exactamente una trae el link de Google News y el título normalizado es idéntico (6 palabras o más) o uno es el inicio cortado del otro, con fechas a ±2 días. Gana el link real. Lo mismo vale contra las notas guardadas (`match_known`). Dos publicaciones con links reales siguen separadas aunque repitan título.
- **El medio guardado no se pisa.** Cuando una nota guardada con link de Google News cambia al link del medio, se queda con su `source_name` si ya tenía uno; solo toma el de la nota nueva si estaba vacío.
- **Mejor link.** Si una nota guardada tenía el link de Google News y su texto fue de respaldo, y ahora llega el link del medio (`refreshes_link`), el link se cambia en el guardado. Ese cambio ya existía (ADR-0025) y respeta la llave única de `url_hash`. Lo nuevo es que el texto **se vuelve a leer y la IA la vuelve a juzgar** (`DedupedArticle.refresh_text`, `StoredArticle.extraction_status`). Si ya se había leído completa, no se paga otra vez.

### 6. Créditos: una sola cuenta

- `searchapi` y `searchapi_web` comparten cuenta (`credit_account`) y tope mensual (`SEARCHAPI_MONTHLY_CREDIT_LIMIT`).
- `credits_used_since` recibe varios proveedores. La estimación y `ExecuteQueries` suman lo de los dos.
- Los mensajes dicen «SearchApi (noticias + web)».
- **Saldo real de la cuenta** (revisión del 18/11/2026). El tope local cuenta lo que gastó este sistema, pero la cuenta de prueba tenía 46 créditos que no se renuevan. `GET https://www.searchapi.io/api/v1/me` (https://www.searchapi.io/docs/account-api) dice cuántas búsquedas le quedan y no gasta créditos (tres llamadas el 18/11/2026; el saldo solo bajó con la búsqueda real, de 47 a 46).
  - `CreditBalancePort` (aplicación) y `SearchApiBalance` (adaptador) leen `account.remaining_searches` o, si no viene, `account.remaining_credits`. Lo guardan en memoria 5 minutos (`BALANCE_CACHE_SECONDS`); si falla, devuelven `None` y vuelven a preguntar al minuto. Con la llave rechazada, el saldo es 0.
  - `PlanSearch` usa el menor entre el saldo y lo que deja el tope local; si el saldo no se puede leer, solo el tope. `/sources` enciende una fuente de pago solo si queda más de 0 y dice cuántos quedan (`credits_remaining`). La estimación lo cuenta en `over_limit`, y `StartSearch` responde «La cuenta de SearchApi (noticias + web) no tiene saldo para esta búsqueda» (`credit_limit_reached`, con `saldo_de_la_cuenta`).
  - Solo lo usan la API (búsqueda manual y rápida). Las corridas automáticas y `make buscar` siguen con el tope local. `SEARCHAPI_BALANCE_CHECK=false` lo apaga; las pruebas lo apagan para no salir a internet.

### 7. Búsqueda rápida

- Sin fuentes elegidas usa `QUICK_DEFAULT_SOURCES` (`google_news_rss,indice_local,searchapi_web`). La manual **no** lo enciende por defecto (`MANUAL_DEFAULT_SOURCES=google_news_rss,indice_local`): manda una consulta por concepto, y una búsqueda de la FGR con sus subdivisiones gastaría varios de los créditos que no se renuevan. Ahí se enciende con su switch. Las corridas automáticas no cambian (`AUTOMATIC_SOURCES`).
- `/sources` dice en cada fuente si va encendida en la manual (`default_on`) y en la rápida (`quick_default_on`). Mientras el analista no toque los switches, la barra de búsqueda rápida usa las de `quick_default_on` y lo dice debajo («Incluye Google web: 1 crédito»). Si los toca, las dos usan lo que eligió; reabrir una búsqueda del historial no borra esa elección.
- Si Google web no alcanza los créditos del mes o el saldo de la cuenta, la búsqueda rápida **no falla**: se lanza sin Google web y la respuesta trae `notice`, «Sin créditos de Google web: se buscó en noticias». Solo falla si ni así cabe (el analista encendió también Google News de pago) o si Google web era la única fuente.

**En pantalla** (revisión del 18/11/2026):

- Si el analista no ha tocado los switches de fuentes, la búsqueda rápida manda las que `/sources` trae encendidas para ella (`quick_default_on`), con Google web. Si ya eligió las suyas, se respetan, aunque no incluyan Google web.
- Reabrir una búsqueda guardada copia sus fuentes para poder ajustarla, pero eso no cuenta como elección del analista (`sourcesChosen` en el estado de Explorar): la búsqueda rápida sigue con las de por defecto. En el navegador de Benji las fuentes guardadas venían de una búsqueda hecha antes de Google web y lo dejaban fuera sin que él tocara nada. Lo guardado antes de este cambio no trae la marca y cuenta como no elegido.
- Los avisos se ven en letra chica, con un icono de alerta, en la consola del barrido, en el expediente y en el panel del diseño de columna: el `notice` del lanzamiento (solo en esa búsqueda) y `progress.notice` del worker, durante y después. Si los dos dicen lo mismo, se muestra una vez.
- Si `/sources` dice cuántos créditos le quedan a una fuente de pago (campo `credits_remaining`), el switch lo dice junto a «Gasta créditos»: «Gasta créditos · quedan 46», o «Sin créditos» con 0. Si no viene, o no es un número entero, el switch se ve como antes.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Otro proveedor de resultados de Google (Serper, la API de Google) | La Custom Search JSON API está cerrada a clientes nuevos (ADR-0003). SearchApi ya está contratado, con la misma llave y los mismos créditos. |
| Seguir las redirecciones `goto` con `follow_redirects` | Descargaría la página del medio o de la red (muros de inicio de sesión, páginas pesadas) solo para saber su dirección. Leer `Location` basta. |
| Esperar entre links o reintentar hasta que Google redirija | Sería insistir contra su verificación de robots. Se prefiere quedarse con el link de Google, que abre igual. |
| Descartar los `goto` sin resolver (lo que se hacía antes) | Se perdían casi todas las publicaciones de redes, justo lo que Benji pidió ver. |
| Guardar la plataforma en una columna nueva | Pide migración y no sirve para las notas viejas. Con lo que ya se guarda se calcula igual. |
| Una consulta por palabra clave, o todas con OR | Cada consulta cuesta un crédito y quedan 47. Google web rinde con el texto tal como lo escribe el analista. |
| `verbatim` para que Google no cambie el texto | Con fechas, Google ignora el filtro de tiempo. `nfpr=1` evita la autocorrección sin perder el periodo. |
| Descargar las publicaciones de redes | Piden iniciar sesión. Lo que se bajaría es la página de acceso, no la publicación. |
| Juntar las redes por título como las noticias | Las publicaciones de una página repiten título: se volverían una sola. |
| Tirar las notas sin fecha de Google web | Muchas de las de redes no traen fecha: se perdería justo lo que Benji pidió. Google ya filtró por periodo. |
| Que la búsqueda rápida responda «tope de créditos» | Cuando se acaben los 47 créditos, la búsqueda rápida dejaría de funcionar aunque las fuentes gratis sí respondan. |

## Consecuencias

- La búsqueda rápida gasta **1 crédito por búsqueda** mientras haya. Con 47, son 47 búsquedas rápidas; después sigue sola sin Google web.
- La búsqueda manual no gasta créditos salvo que el analista encienda Google web o Google News de pago. Con saldo 0, los switches de pago salen apagados. `make buscar` usa las fuentes por defecto de la manual y muestra el costo antes de pedir «si».
- «Probar concepto» muestra la consulta de Google web y suma su crédito al costo estimado, porque Google web es una fuente ofrecida.
- Las publicaciones de redes se juzgan con título y fragmento, sin el cuerpo. Su resumen es más pobre.
- Las noticias destacadas que solo trajo Google web quedan en «Otros sitios» (la sección no se guarda). Las notas viejas guardadas con «Noticias · <medio>» conservan ese texto en `source_name`; desde la revisión del 18/11/2026 ya no cuentan como noticia por esa marca.
- Las fechas relativas («hace 5 días») tienen un día de redondeo. Por eso la regla de títulos cortados usa ±2 días.
- Los resultados con link de Google no se juntan con la misma publicación guardada con su link real, porque el link es otro. Pueden salir **repetidos entre búsquedas**: una con el link de Google y otra con el real.
- `# VERIFICAR`: no está documentado cuánto dura un link `goto`. Si Google lo vence, abriría su página y no la publicación; el título, el fragmento y la red siguen bien.
- Si Google cambia sus redirecciones `goto` (por ejemplo, si pide aceptar cookies), esos resultados se quedan con su link de Google sin tumbar la búsqueda. Llegan con menos datos, no notas falsas.
- Hay que verificar con la cuenta real qué código y qué texto responde SearchApi sin saldo (`# VERIFICAR` de 402/429) y el formato de `inline_tweets`, que no vino en la respuesta grabada.
