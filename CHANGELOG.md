# Historial de cambios

Todos los cambios importantes de este proyecto se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [versionado semántico](https://semver.org/lang/es/): cada fase N cierra con la versión `v0.N.0`.

## [Sin publicar]

### Agregado

- **Fase 12 — Monitor automatizado FGR: plan y decisiones iniciales.** El plan de Benji queda en `docs/PLAN_MONITOR_FGR.md`, con los ajustes acordados el 24/10/2026:
  - una búsqueda nacional por corrida, repartida por estado;
  - corridas automáticas a las 07:00, 15:00 y 23:00 solo con fuentes gratis (Google News RSS e índice local);
  - SearchApi y BrowserWork (Bing, Google 2) como switches de la búsqueda manual;
  - duplicados en tres niveles y tema visual homologado con OSINT Oráculo.

  El reloj de Celery que ya existe dispara las corridas (ADR-0022). Los perfiles de fuentes y la conexión con BrowserWork quedan en el ADR-0023.
- **`make reparar-texto`** (F12.1, ADR-0024): repara el Mojibake de las notas ya guardadas en el índice local, en las notas y en sus textos, y recalcula sus columnas de búsqueda. Sin opciones solo muestra cuántas cambiarían y 5 ejemplos reales; con `ARGS=--aplicar` pide «si» y guarda por lotes.
- **Switches de fuentes** (F12.2, ADR-0027): en la búsqueda manual el analista enciende o apaga Google News RSS, el índice local y SearchApi; cada switch dice si es gratis o gasta créditos, y la estimación se recalcula (con SearchApi apagado, 0 créditos). La búsqueda guarda sus fuentes (migración 0025, `searches.providers`), el worker corre solo con ellas, la bitácora las registra y el historial las muestra. Cada fila de la lista dice de qué fuente vino la nota. Nuevo `GET /sources`; `MANUAL_DEFAULT_SOURCES` fija las encendidas por defecto.
- **BrowserWork como fuente, listo pero oculto** (F12.3, ADR-0028): adaptador para Bing y Google 2 por la API de BrowserWork, sin llave ni credenciales. Si pide captcha, falla o no termina en 240 s, esa fuente se omite y la búsqueda queda parcial. Se configura con `BROWSERWORK_BASE_URL`. En la prueba real del 25/10/2026, Bing trajo solo sitios oficiales y Google 2 links rotos por un error de BrowserWork, así que sus switches quedan ocultos hasta que se corrija.
- **Cronología vertical** (26/10/2026, ADR-0032): en lugar de la línea del tiempo de abajo, un panel en la izquierda, debajo de la búsqueda, como un feed en vivo. Lleva una línea luminosa con la hora y cada hecho, del más reciente al más viejo y agrupados por día, sin repetidos: el mismo hecho en varios medios es una sola entrada («+7 medios»). Arriba tiene una curva de notas por hora (un clic filtra esa hora) y los filtros por categoría y estado. El globo queda libre en el centro. La lista de noticias del panel izquierdo queda oculta y vuelve con «☰ Lista».
- **Temas en la cronología** (26/10/2026, ADR-0032): cuando un nombre propio sale en 5 hechos o más, esos hechos se juntan en un bloque que se despliega, por ejemplo «TEMA · Jáuregui · 27 hechos · 61 notas», con lo último que pasó. En la corrida FGR del 26/10 la cronología bajó de 65 renglones a 31. Al elegir un hecho, el desglose dice qué medios lo publicaron, entre qué horas y con qué titular, sin repetir lo que ya dice la ficha del globo.
- **Categoría «Seguridad nacional (traición a la patria)»** (26/10/2026, ADR-0029): el 72 % de las notas de las corridas FGR caía en «Otros», y la IA proponía sola «traición a la patria» en 90 de ellas. La migración 0029 agrega la categoría antes de «Otros». El prompt `classify_v4` pone lo que rodea a un caso penal (protestas, cartas, audiencias) en la categoría del delito. Las notas se vuelven a clasificar con `make clasificar ARGS=--aplicar`.
- **Reporte: una ficha por hecho** (26/10/2026, ADR-0033): el mismo hecho en varios medios es una sola ficha, con «También lo publicaron» (medio, hora y link). El reporte de la corrida de las 15:00 pasó de 143 fichas y 33 páginas a 76 fichas y 22 páginas. El análisis completo está en `docs/analisis-2026-10-26.md`.
- **Fondo del espacio nítido** (26/10/2026, ADR-0017): el cielo ya no se ve pixeleado. La cámara del cielo ve 60° en lugar de 37°, la textura 8K de la NASA se usa siempre que la tarjeta la acepte, el lienzo sigue la escala de la pantalla (antes se quedaba a 1× si arrancaba con otra) y un punto negro sustituye al aclarado parejo, así que el fondo queda negro y sin bruma. Las estrellas propias son más reales: redondas, con colores de estrella y casi sin titilar.
- **Búsqueda y cronología se ocultan por separado** (26/10/2026): «Ocultar ‹» pliega solo la búsqueda a un renglón y la cronología se pliega con su propio «›». La búsqueda terminada quedó más compacta (qué se buscó, sus datos con «Editar» y «‹ Volver», y las descargas), así la cronología gana alto. Los créditos solo se muestran si se gastaron.
- **Entrada sobre el Atlántico y atmósfera más suave** (26/10/2026): al abrir el sistema el globo llega girando al Atlántico y de ahí sigue su giro normal. El halo de la atmósfera bajó al 60 % y la aureola pasó de cian a un tono apagado, casi gris, porque se veía demasiado azul.
- **Globo, más cerca y con aureola:** una aureola cian muy tenue y el brillo del Sol asomándose por el borde, que se apagan al acercarse. Al elegir una nota, la cámara llega casi al lugar de los hechos (localidad a zoom 14.5, municipio a 11.5) con inclinación de 45°.
- **Globo:** las imágenes de la NASA ganan color y contraste, y de noche resaltan las luces de las ciudades. La iluminación sigue pareja: el día y la noche los elige el analista.
- **Reporte PDF Oráculo** (F12.10, ADR-0033): portada de hoja completa con red de nodos, número de expediente y banda «USO INTERNO · CONFIDENCIAL». Trae tarjetas por categoría, el mapa de México con porcentajes más barras apiladas por delito en cada estado, la línea del tiempo con sus 3 picos y las noticias divididas Estado › Categoría › Nota, con marcadores plegables en el lector de PDF e insignias de confianza (categoría, quién actúa, ALTA/MEDIA/BAJA). Títulos en Orbitron. Los emojis ya no salen como cuadros vacíos. Las corridas automáticas lo dejan en `data/reportes/`.
- **Línea del tiempo** (F12.7, ADR-0032): abajo en Explorar, las notas de la búsqueda por hora o por día (hora de la CDMX), con los 3 picos resaltados. Elegir una barra filtra ese tramo; también se filtra por categoría y por estado. El globo, la lista y la línea del tiempo muestran siempre las mismas notas. Una tira las ordena por cuándo ocurrió el hecho (◆) o por cuándo se publicaron (●), y elegir una nota vuela el globo hacia ella.
- **Monitor automático FGR** (F12.8, ADR-0031): el reloj de Celery corre tres búsquedas al día (07:00, 15:00 y 23:00, hora de la CDMX) de la FGR en todo México, hoy y ayer. Usa solo Google News RSS y el índice local (GDELT y medios), así que gasta 0 créditos. Cada corrida pasa por el mismo proceso que una manual (resumen, ubicación, categoría, quién actúa, historias), guarda su reporte en PDF en `data/reportes/` y aparece en el historial de todos con «Monitor automático · corrida de las 07:00». La migración 0028 agrega `searches.trigger`, `searches.scheduled_for` y `reports.pdf_path`. `make corrida-fgr` corre una en el momento. Primera corrida real (26/10/2026): 162 notas, 104 relevantes para la FGR, 0.047 USD.
- **Tema Oráculo** (F12.7a): el monitor usa los colores y tipografías de OSINT Oráculo: fondo `#050505`, cian `#00d2ff`, títulos en Orbitron y texto en Roboto, autoalojadas. La marca y la pestaña activa llevan el brillo cian de OSINT.
- **Solo el concepto FGR** (F12.6): `make retirar-conceptos` retiró los 11 conceptos anteriores con borrado lógico, así que el historial, los casos y los reportes siguen intactos (aplicado el 26/10/2026, respaldo previo). El concepto FGR ya tiene la descripción estricta del plan. `make seed` ahora carga solo el concepto FGR, con su regla `fgr_federal`.
- **Relevancia FGR federal** (F12.5, ADR-0030): en las búsquedas de la FGR solo cuentan las notas donde actúa la FGR federal. Ya no cuentan las de una fiscalía estatal (como la fosa común de San Luis Potosí) ni las que solo la nombran de pasada. La IA dice quién actúa al clasificar cada nota (prompt `classify_v2`, en la misma llamada que la categoría) y el concepto FGR lleva la regla `fgr_federal`. Esas notas no se borran: pasan a «No relevantes», con su razón. La ficha dice «Quién actúa». `make clasificar ARGS="--notas …"` prueba casos elegidos. La migración 0027 agrega `articles.authority` y `concepts.relevance_rule`.
- **Categoría de cada nota** (F12.4, ADR-0029): la IA clasifica cada nota por el delito del que trata en una de 14 categorías provisionales (Narcotráfico, Secuestro, Huachicol, Corrupción… y «Otros»), en lotes de 25 con título y resumen, y guarda además la etiqueta libre que propone («robo de combustible») para decidir después las categorías definitivas. Cada búsqueda clasifica al cerrar sus notas; si falla, la búsqueda no se cae. Nuevo `GET /categories`; cada nota trae `category` y `category_raw`, y los agregados cuentan por categoría (`by_category`). `make clasificar` clasifica las ya guardadas: sin opciones 5 de ejemplo sin guardar; con `ARGS=--aplicar` todas. La migración 0026 agrega el catálogo y `articles.category_id`.
- **`make comparar-fuentes`** (F12.2): hace la misma consulta en SearchApi y Google News RSS y dice cuántas notas trajo solo cada una y cuántas las dos, con 5 ejemplos de lo que solo trajo SearchApi. Gasta hasta 3 créditos y pide «si».
- **Historias** (F12.1c, ADR-0026): las notas del mismo hecho publicadas por varios medios se juntan en una historia, sin borrar ninguna. Cada búsqueda agrupa al cerrar sus notas con las de los días cercanos; `make agrupar-historias` lo hace con las ya guardadas (sin opciones solo muestra 5 historias; con `ARGS=--aplicar` pide «si»). Con las notas del 24/10/2026: 172 historias con 491 notas, de 1,450 a ~1,131 tarjetas. La migración 0024 agrega `articles.story_id`.
- **`make limpiar-duplicados`** (F12.1b, ADR-0025): quita del índice local las notas repetidas que entraron antes: la misma URL con otra forma (`:443`, `www.`), el mismo medio con el mismo texto y cuerpo, y títulos sin letras. Sin opciones solo muestra conteos y 5 ejemplos reales; con `ARGS=--aplicar` pide «si» y borra por lotes. No toca notas de búsquedas, casos ni reportes.
- **El muro del caso sobre el globo** (Fase 9.6, historia H9.3):
  - **Abrirlo:** «🌐 Ver en el globo» en el detalle del caso (o `#/explorar?caso=<id>`, que se puede compartir) vuela a donde ocurrió el caso.
  - **Qué se ve:** cada entidad confirmada es un nodo que late, con color por tipo y borde por estatus legal; los vínculos son arcos de luz, punteados si están sugeridos.
  - **Al elegir una entidad:** la cámara la orbita, lo demás se atenúa y entra un panel con su estatus legal, sus vínculos (un clic vuela a la otra entidad) y sus citas.
  - **Constelación:** las notas del caso aparecen como puntos de luz unidos por las entidades que comparten.
  - **Base técnica:** el servidor calcula las posiciones (`GET /cases/{id}/graph`) y las personas se reparten alrededor del lugar de sus notas sin encimarse. Abrir el muro queda en la bitácora.
- **Mis casos en el globo** (Fase 9.6): el interruptor «Mis casos» pone cada caso abierto como marcador ámbar; un clic abre su muro (`GET /cases/map`).
- **Limpiar el globo** (Fase 9.6): «✕ Limpiar globo» y «Nueva búsqueda» quitan lo pintado y dejan el formulario listo para otra búsqueda con la misma región, conceptos y fechas. La búsqueda anterior sigue en Historial.
- **Duplicados y vínculos de un caso** (Fase 9.5, §9.8, ADR-0106):
  - **Posibles duplicados:** el sistema sugiere qué entidades del caso podrían ser la misma (mismo nombre, un nombre o alias en común, o nombres muy parecidos) y las muestra lado a lado con sus citas. Solo una persona decide «Son la misma» o «No son la misma»; nada se une solo. Al unir queda la confirmada.
  - **Deshacer:** «separar» deshace una fusión, y «Separar menciones» saca a un homónimo que quedó junto.
  - **Vínculos:** «aparecen juntas» se sugiere entre entidades confirmadas que comparten notas del caso, con confianza de 0.5 a 0.9 según cuántas compartan. El analista también dibuja vínculos («familiar», «es dueño de», una etiqueta propia…), que nacen confirmados con su firma.
  - **Bitácora:** cada decisión queda registrada.
  - **Base:** la migración 0022 guarda los «No son la misma».
- **Entidades de un caso** (Fase 9.4, historia H9.2, ADR-0103): al agregar una noticia a un caso, la IA la lee en el worker y propone personas, organizaciones, lugares y vehículos, cada uno con su estatus legal según la nota (nunca "culpable") y una cita literal comprobada contra el texto. Lo que no está escrito en la nota se descarta. En el caso, la sección Entidades muestra sugeridas, confirmadas y descartadas con sus citas, el avance y el costo de la IA, y «Analizar con IA» para las notas pendientes. Confirmar a una persona exige elegir su estatus legal; todo queda firmado en la bitácora. Nuevo prompt `entities_v1`, migración 0020 y `make extraer-entidades` para ver ejemplos reales antes de gastar.
- **Agregar al caso** en la ficha de cada noticia (Fase 9.3, historia H9.1): lista mis casos abiertos con ✓ en los que ya la tienen, crea un caso nuevo en el mismo paso y deja el último caso usado a un clic («+ Agregar a «Homicidio estilista Polanco»»), así 8 notas seguidas son 8 clics. La ficha dice en qué caso está la nota.
- **Pestaña Casos** (Fase 9.3): lista de mis casos (activos o archivados) con estado, sensibilidad y número de notas; crear y editar un caso; cerrarlo, archivarlo o reabrirlo; y ver sus noticias con «Ver nota original» y «Quitar». Un caso cerrado es de solo lectura.
- **Fase 9.3 — Casos de investigación (API):** `GET/POST /cases`, `GET/PATCH /cases/{id}`. Cada persona ve solo sus casos (un caso ajeno responde 404, igual que uno inexistente), quien crea un caso queda como dueño, un lector no edita (403) y un caso cerrado solo cambia de estado (409). Crear, editar, cerrar, reabrir y **abrir** un caso quedan en la bitácora; la vista, una vez por persona cada 5 minutos. Las noticias se agregan (`POST /cases/{id}/articles`, sin duplicar con un doble clic), se quitan sin borrarlas del sistema y se listan con el formato de Explorar. El dueño administra quién más ve el caso (`/cases/{id}/members`: editor o lector) y el caso nunca se queda sin dueño.
- **Fase 9.2 — Modelo de datos del tablero de investigación** (migración 0018): tablas `entities`, `entity_aliases`, `entity_mentions`, `relationships` y `external_links` (reservada y vacía, ADR-0101). La base garantiza las reglas de la fase: el estatus legal solo admite lo que dice una nota (mencionado, señalado, detenido, vinculado a proceso, víctima, testigo, funcionario) y nunca "culpable"; todo nace sugerido y confirmar o descartar exige quién y cuándo (ADR-0104, 0105); la evidencia es una cita de 300 caracteres como máximo. Vocabulario en `app/domain/investigation.py`. La migración 0019 agrega los casos: `cases`, `case_members` (acceso por caso, un solo dueño), `case_articles`, `case_entities` y `case_notes` (ancladas a lo más a una cosa), más el índice de la bitácora por usuario para saber quién vio qué caso.
- **Fase 9.1 — Motor visual del muro** (ADR-0102): laboratorio solo para desarrollo (`?laboratorio`, pestaña "Laboratorio") que dibuja un caso de investigación sobre el mismo globo de Explorar y mide fps con un guion fijo de cámara (giro, vuelo, órbita y zoom 14 en Polanco) contra el globo sin muro. Con 150 nodos, la capa propia de MapLibre resta de 1 a 20 % de los fps según el paso y deck.gl de 17 a 31 %; a zoom 14 deck.gl además dibuja los arcos escalonados. Se elige la capa propia y se quita deck.gl. En este equipo el globo solo no llega a 60 fps en vuelos, así que el criterio queda relativo al globo sin muro; la órbita y el vuelo todavía pasan del 10 % y se ajustan en la 9.6.
- SearchApi trae hasta 3 páginas por consulta (30 notas de Google en lugar de 10). Pide la siguiente solo si la anterior vino llena; cada página cuesta 1 crédito (medido con la cuenta) y la bitácora registra lo gastado de verdad. La estimación dice "hasta N créditos". Configurable con `SEARCHAPI_MAX_PAGES` (ADR-0019).
- Al hacer clic en un grupo de notas, o en notas encimadas en el mismo punto, aparece la lista de cuáles son; elegir una vuela a ella y "Acercar" separa el grupo.
- La ficha de una nota dice la fecha del hecho cuando es de otro momento ("Fecha del hecho: 29 sep 2025" en un avance de un caso viejo) y "lugar mencionado" cuando la ubicación no es la del hecho.
- Aviso al terminar una búsqueda: "✓ Búsqueda lista: 18 notas" abajo al centro de Explorar durante 8 s y, si la pestaña estaba oculta, también en su título hasta que la persona regresa. Reabrir una búsqueda del Historial no avisa.

### Cambiado

- **El mundo gira desde que abre el sistema** (27/10/2026): la entrada desde el espacio frena parejo hasta la velocidad del giro y el globo sigue girando sin pausa. Antes pasaban unos 4 s con el mundo casi quieto y parecía que el sistema se trababa. Mientras cargan las fotos de la NASA, el globo se ve como un océano oscuro y no como un disco blanco.
- **El universo detrás de todas las pestañas** (26/10/2026, ADR-0017): Casos, Conceptos, Historial y Estado ya no tienen el fondo azul-negro liso. Detrás va el mismo universo de Explorar, que deriva muy despacio, con un velo oscuro y dos auroras cian que se mueven lento para que el texto se lea. Es un solo fondo para toda la aplicación, ligero (unos 22 cuadros por segundo).
- **Encabezado nuevo, centrado y sin fondo** (26/10/2026): la marca y las pestañas van en un solo grupo al centro, sobre las estrellas; en Explorar el universo y el globo siguen detrás del encabezado. La marca es la «marca-signal» de OSINT Oráculo (Orbitron): el nombre con un destello cian que lo recorre, «Oráculo · Noticias geolocalizadas» con un barrido de radar abajo y el globo con un aro que late y un meridiano que gira. Las pestañas llevan una línea cian que crece bajo la activa. Con «menos movimiento» del sistema no hay animaciones.
- **Solo la descarga del PDF, por ahora** (26/10/2026): de la búsqueda se quitaron los botones de CSV, GeoJSON e Imprimir; queda un botón «Descargar reporte (PDF)». Las rutas de la API siguen, y para volver a mostrarlos basta agregarlos a `VISIBLE_DOWNLOADS`.
- **Google News RSS activo también en producción** (ADR-0021, sustituye al ADR-0011): por dictamen de la Dirección del 24/10/2026, las búsquedas vuelven a consultar el RSS de Google News, gratis, además de SearchApi y el índice local. Antes estaba apagado por los términos del feed. `NEWS_RSS_ENABLED=false` lo apaga sin tocar código, y se quitó la advertencia de «solo desarrollo».
- Historial: el periodo de cada búsqueda se lee como en Explorar ("13 – 20 oct 2026") y no como fechas técnicas ("2026-10-13 a 2026-10-20").
- La lista de Explorar dice cuántas notas se ven de cuántas trajo la búsqueda ("Noticias (24 de 43)"); antes decía "Noticias (24)" mientras arriba decía "43 notas" y parecía que faltaban. La ayuda del encabezado y de los botones PDF, CSV y GeoJSON aclara que las descargas incluyen solo las notas relevantes.
- El buscador de regiones (Explorar y "Probar concepto") dice de qué estado es cada municipio o localidad: "Municipio San Pedro — Coahuila de Zaragoza" y "San Pedro Garza García — Nuevo León". Antes solo mostraba la clave INEGI y había que sabérsela para distinguir homónimos.
- Prompt de la IA `enrich_v2`: pide el municipio o alcaldía de cada colonia, calle o lugar (`municipality_hint`), marca al menos un lugar del hecho cuando se puede saber, fecha el hecho original en avances de casos viejos y no confunde el Día de Muertos con homicidios. Las notas leídas con v1 se vuelven a leer en la siguiente búsqueda que las encuentre.
- Vuelos del globo más fluidos: mientras vuela a una región, a una nota o a un grupo, el mapa se dibuja al 80 % de la resolución de la pantalla y recupera la nitidez al aterrizar (`map/flight.ts`). Medido a 1920×1080 con escala 125 %: de ~37 a ~46 cuadros por segundo y de 30 % a 12 % de cuadros lentos. El giro lento del globo no cambia.
- Explorar en pantallas bajas: al terminar, la búsqueda se reduce a un renglón ("Extorsión · Jalisco · 10 – 17 oct 2026 · 18 notas…") con "Editar" y una fila de descargas (PDF, CSV, GeoJSON, Imprimir), y la lista de noticias se queda con el resto. A 1366×650 pasan de 2 a 3–4 noticias visibles. "Ocultar ‹" esconde el panel para ver el globo completo; en celular se oculta solo al elegir una noticia.
- Celular: las pestañas de arriba bajan a su propio renglón y caben en 375 px (antes la página se desbordaba a 451 px).
- Modo día: al acercarse, el mapa de calles ahora es claro (antes siempre usaba la variante oscura de Protomaps y parecía de noche). `make geo-basemap` baja también los íconos claros.
- Explorar ya no muestra las gráficas "Top 5 estados con más noticias" ni "Tipos de noticias" (decisión de Benji: no aportaban y estorbaban). La derecha queda libre para el globo; el reporte en PDF conserva su página de análisis.
- Los créditos del mapa (INEGI, Natural Earth, NASA, OpenStreetMap) empiezan plegados en Explorar: solo se ve el botón "i" y aparecen al hacer clic. Antes MapLibre los dejaba abiertos porque el giro del globo no cuenta como arrastre.

### Corregido

- **Los menús desplegables ya no salen blancos** (27/10/2026): las opciones de los filtros (categoría, estado) tenían fondo blanco y texto cian claro, casi ilegible; ahora tienen el fondo y el texto de Oráculo.
- **La ficha de una nota ya no choca con el encabezado y se puede arrastrar** (27/10/2026): nunca sube detrás de Casos, Conceptos, Historial… y se mueve con el mouse desde cualquier parte que no sea un link o un botón; la línea al punto la sigue. Al elegir otra nota vuelve a su lugar.
- **El globo ya no se cae en tarjetas de video integradas** (26/10/2026, ADR-0017): en la Intel UHD de Benji, Chrome le quitaba el 3D a la página. Ahora la foto del cielo se sube en 8 piezas (la tarea más larga de la carga bajó de 550 a 158 ms), el fondo solo se dibuja cuando la cámara se mueve (0 dibujos con el globo quieto), Explorar se queda montada al cambiar de pestaña, sin crear el globo otra vez, y el mapa base del mundo ya no se dibuja debajo de la foto de la NASA (−22 % de dibujos al girar). Si aun así se pierden los gráficos y no vuelven en 6 s, el globo lo avisa.
- **Descargar el PDF ya no deja la pantalla en blanco** (26/10/2026): si la tarjeta de video se reinicia y Chrome bloquea los gráficos 3D de la página, el globo muestra un aviso con «Recargar». La búsqueda, la cronología y el PDF siguen funcionando. Antes, el error al crear el globo desmontaba toda la aplicación.
- **El mismo hecho ya no se parte cuando un caso domina** (ADR-0026): la vinculación a proceso de Jáuregui quedaba en unas 12 historias, porque sus palabras salían en decenas de títulos y dejaban de contar como poco comunes. Ahora basta un parecido por palabras de 0.75 o más con 3 palabras en común, y la nota entra a la historia más parecida, no a la más antigua. La corrida FGR pasa de 94 a 87 hechos. Se reagrupó el 26/10/2026, con respaldo previo.
- **Elegir una nota ya no desplaza la pantalla de Explorar** ni deja una franja negra abajo.
- **Google News RSS no se usaba en las búsquedas** (F12.2): el ADR-0021 lo encendió por defecto, pero la lista de proveedores de las búsquedas (`SEARCH_PROVIDERS`, del 17/10/2026, cuando el RSS estaba apagado) nunca lo incluyó; solo `make probar-proveedor` lo consultaba. Ahora cada búsqueda lo consulta (gratis) salvo que el analista lo apague o `NEWS_RSS_ENABLED=false`.
- **Notas repetidas** (F12.1b, ADR-0025): la misma nota que llega en otra búsqueda con otro link (Google News y el del medio) ya no se guarda dos veces: se reutiliza la guardada, con su resumen de IA, y se prefiere el link del medio. El índice local tampoco guarda dos veces la misma URL (`:443`, `www.`) ni el mismo texto y cuerpo del mismo medio a ±3 días, ni «notas» cuyo título es solo un emoji. La misma nota en otro medio sí se guarda: es otra fuente.
- **Títulos con «letras raras»** (F12.1, ADR-0024): `seÃ±alÃ³`, `JÃ¡uregui` o `ChihuahuaðŸŽ¦` ahora entran como `señaló`, `Jáuregui` y `Chihuahua🎦`, vengan de GDELT, de un RSS o de cualquier proveedor. Venían de GDELT en cinco medios (396 notas del índice al 24/10/2026). El texto correcto no se toca.
- Entidades de un caso: "Eduardo “N”", "Eduardo 'N'" y "Eduardo N" quedaban como tres sugerencias distintas de la misma persona, porque las comillas del medio contaban al comparar nombres (en el caso de prueba, 8 pares así). Ahora se comparan sin comillas (`entity_name_norm`) y la migración 0021 corrige los nombres ya guardados; las sugerencias que ya estaban separadas se ofrecen para unir en la 9.5, nunca se juntan solas.
- Modo día: sobre el mapa claro de calles, los paneles translúcidos de Explorar quedaban grises y la línea "medio · fecha · lugar" de cada noticia casi no se leía (contraste 1.6 : 1 medido en pantalla). En modo día el vidrio se oscurece y esa línea va un tono más clara: 6.1 : 1. De noche no cambia.
- Buscador de regiones con errores de dedo: "monterey" ponía primero el país Montenegro y después el municipio Monterrey, porque en las coincidencias aproximadas mandaba el nivel (país antes que municipio) y no el parecido. Ahora, cuando el nombre solo se parece, gana lo más parecido; lo exacto y lo que empieza igual siguen ordenados por nivel.
- "Probar concepto" decía "4 consultas" (SearchApi, Google News RSS, GDELT e índice local) aunque una búsqueda real solo manda 2: SearchApi y el índice local. Ahora muestra solo los proveedores configurados, los mismos que usa la estimación de Explorar.
- El reporte PDF de una búsqueda en la localidad cabecera homónima ("Localidad Miguel Hidalgo", 090160001) decía "0 en Miguel Hidalgo · 0 %" y todo "fuera de la región", mientras la pantalla mostraba 8 de 11 notas dentro. El reporte ahora cuenta y dibuja el mapa sobre la alcaldía con la misma regla que el geolocalizador (`seat_area`, ADR-0020): en esa búsqueda, 8 dentro (73 %) y 3 fuera.
- Los créditos del mapa (OpenStreetMap, Protomaps) abrían en la misma pestaña; ahora en otra, igual que "Ver nota original".
- Ubicaciones equivocadas o vacías por colonias y palabras genéricas (ADR-0020). "Polanco, CDMX" terminaba en una localidad de Jalisco y "Dos Bocas" (Tabasco) en Veracruz: el estado que da la IA ya no se descarta. "alcaldía Miguel Hidalgo" o "colonia Roma Norte" no se encontraban: se quita la palabra genérica antes de buscar. Lo que INEGI no tiene se busca en ~107 mil colonias y zonas de OpenStreetMap (tabla nueva `places`, `make geo-places`, sacadas del mapa base ya descargado) y se pinta en la colonia ("Polanco, Alcaldía Miguel Hidalgo"). Si solo se sabe el estado, la nota se ubica ahí como aproximada. Con el municipio que sugiere la IA, una colonia homónima de otra alcaldía ya no gana ("Ajusco, Tlalpan" no es la Colonia Ajusco de Coyoacán) y, si no hay colonia, la nota queda en ese municipio. "El Rosario" encuentra el municipio "Rosario". Buscar la localidad cabecera homónima ("Miguel Hidalgo", 090160001) cuenta como buscar su alcaldía: antes todo lo de Polanco salía "fuera de la región". La ubicación principal prefiere el lugar del hecho dentro de la región buscada y, si la IA no marcó ninguno, el lugar mencionado dentro de ella.
- Al saltar entre notas la animación del globo empezaba a fallar: los vuelos fluidos bajaban la resolución con el mapa quieto, y MapLibre en ese caso detiene lo que se mueve y avisa "terminó de moverse", así que se cortaban vuelos y la ficha salía antes de tiempo. Ahora la resolución baja con el vuelo ya en marcha.
- Elegir una nota siempre vuela con el mismo zoom según la precisión de su lugar (localidad 11, municipio 9, estado 5, país 4); antes era "el mayor entre el actual y ese" y, ya de cerca, otra nota no acercaba nada. Volver a elegir la misma nota vuelve a volar y la ficha aparece al llegar. Fuera de México el zoom se queda en 6.5: más cerca no hay mapa de calles (solo se descargó el de México; el del mundo pesaría 559 MB hasta zoom 8, 1.6 GB hasta 9 y 3.8 GB hasta 10).
- Al elegir un país grande o con territorios lejanos (Estados Unidos, Rusia, Canadá, Francia, Noruega…) el globo se alejaba o se iba al Atlántico. Dos causas: el rectángulo del país incluía todo su territorio (Francia de Guadalupe a Reunión; Estados Unidos y Rusia cruzan el meridiano 180, así que cubrían el mundo) y MapLibre encuadraba como si el mapa fuera plano, donde el Ártico se estira sin fin. Ahora cada región tiene `focus_bbox` con su parte principal (columna nueva, migración 0016; también lo usa el mapa del reporte) y el globo mide el encuadre sobre la esfera. Colima ya no incluye las islas Revillagigedo al encuadrar.
- Los países ahora se acercan hasta zoom 6 (antes 4): Países Bajos o El Salvador quedaban lejos.
- El globo no volaba a la región ni a la nota en celular: los márgenes del encuadre eran fijos para escritorio (760 px de ancho) y MapLibre se negaba ("Map cannot fit within canvas"). Ahora se calculan según la pantalla y el panel (`map/framing.ts`); en celular la ficha de la nota va encima del punto y cabe completa.
- En escritorio las regiones quedaban corridas a la izquierda porque el margen derecho seguía reservando el lugar de las gráficas que se quitaron.

## [0.7.0] - 2026-10-19

### Agregado

- **Fase 7 — Reportes** (§15, ADR-0018):
  - `POST /searches/{id}/report?format=pdf|html`: reporte A4 con portada (cifras clave, resumen ejecutivo con IA y datos clave calculados), página de análisis (mapa estático, tabla por subregión con barras, notas por día y medios con más notas), noticias agrupadas en dentro, fuera y sin ubicación, y anexo de metodología y fuentes. Nunca el texto de las notas.
  - Mapa estático en SVG dibujado con PostGIS: subregiones coloreadas por número de notas, vecinas recortadas al marco y anillo punteado para lo poco preciso.
  - Resumen ejecutivo con la IA (`summary_v1.md`) a partir de los resúmenes de las notas, guardado en la tabla nueva `reports` para no volver a pagarlo (~0.0003 USD medido).
  - `GET /searches/{id}/export?format=csv|geojson`: las notas en CSV (UTF-8 con BOM, sin fórmulas de Excel) y GeoJSON.
  - Cada reporte o exportación queda en la bitácora como `report.generated`; una búsqueda que corre responde `409 search_not_finished`.
  - Panel de Descargas activo en Explorar: Reporte (PDF), Datos (CSV), Mapa de puntos (GeoJSON) e Imprimir.
  - `/aggregates` acepta `level=locality`.
  - WeasyPrint 70, Jinja2 y Noto Sans incluida (OFL) para que la Ñ y los acentos salgan iguales en cualquier servidor; el instalador de WSL agrega Pango y HarfBuzz.

## [0.6.0] - 2026-10-17

### Agregado

- **Fase 6 — Frontend: globo y búsqueda** (§14, ADR-0017):
  - Pantalla **Explorar** (inicial): el globo domina la pantalla, con la Tierra de la NASA (de noche con las luces de las ciudades o de día) sobre un fondo de Vía Láctea y estrellas que titilan (three.js), y paneles translúcidos a los lados.
  - `make geo-earth`: descarga Blue Marble, Black Marble 2016 y Deep Star Maps con manifiesto y SHA-256, mezcla la noche con GDAL y genera teselas locales `earth_day.pmtiles` y `earth_night.pmtiles` (zoom 0–6). Al acercarse se funden con el mapa vectorial y las capas de INEGI.
  - Movimiento en un solo módulo (`map/motion.ts`): entrada hacia México, giro que se frena al acercarse y se reanuda tras 25 s sin uso, y vuelos cuya duración depende de la distancia y del zoom (1.2 a 4.5 s), con inclinación según el nivel. Hay control de velocidad (lenta, normal, rápida o sin animación) y se respeta "menos movimiento" del sistema.
  - Panel de búsqueda (§14.3): buscador de regiones, migas de pan, filtros Estado → Municipio → Localidad sincronizados con el globo, conceptos, fechas, estimación de consultas, créditos y costo de IA antes de buscar, y avance por etapas.
  - Resultados sobre el globo: mapa de calor, grupos de puntos, puntos que aparecen en cascada y laten al elegirlos, y anillo punteado para lo ubicado solo por estado o país. Un clic vuela a la nota y abre su ficha (§14.4) con línea guía.
  - Lista de noticias (Dentro, Fuera, Sin ubicación) con el interruptor "No relevantes", que vale para la lista y el globo a la vez; gráficas "Top 5 estados" y "Tipos de noticias", y panel de Descargas (sus botones funcionan en la Fase 7).
  - Pestaña **Historial**: reabre una búsqueda anterior en el globo sin gastar créditos.
  - Estado global con Zustand y servicios y hooks de búsquedas con TanStack Query (consulta el avance cada 2 s).
  - Prueba de humo del flujo principal (H1) con Testing Library y respuestas reales grabadas.

### Eliminado

- Pestaña temporal **Notas**, rutas `/api/v1/local-index/search` y `/stats`, y el globo viejo de **Geodatos**: los reemplaza la pantalla Explorar (Fase 6). El índice local sigue buscando como proveedor dentro de cada búsqueda.

## [0.5.0] - 2026-10-17

### Agregado

- **Fase 5 — API de búsqueda y resultados** (`docs/api.md`, con ejemplos de `curl` reales):
  - `POST /searches/estimate`: consultas, créditos del mes y costo máximo de la IA, sin gastar.
  - `POST /searches`: crea la búsqueda y la manda al worker (`202`). Antes revisa la llave de la IA (`503`), el tope mensual (`409`) y el máximo de consultas.
  - `GET /searches/{id}` (estado, avance y costo) y `GET /searches` (historial con cursor).
  - `GET /searches/{id}/articles`: notas con resumen, conceptos, ubicación y punto. Filtros `relevant`, `in_region`, `precision` y `concept_id`, con cursor por fecha.
  - `GET /searches/{id}/aggregates`: mapa de calor por estado, municipio o país, sin repartir lo menos preciso.
  - `GET /articles/{id}`: todas sus menciones de lugar (nunca el texto completo).
  - Errores 500 y 503 con el formato uniforme y OpenAPI revisado: cada ruta documenta solo sus errores y cada grupo tiene descripción.
  - `PlanSearch`: la API y `make buscar` estiman igual.

### Corregido

- Borrar un concepto que ya se usó en una búsqueda ahora lo desactiva (borrado lógico, §13). Antes `is_used_in_searches` siempre respondía "no" y el borrado físico chocaba con `search_concepts` (error 500).

## [0.4.0] - 2026-10-17

### Agregado

- **Fase 4 — Pipeline, IA y geolocalización.**
  - Tablas de búsquedas y notas (migraciones 0011 a 0013):
    - `searches` y `search_concepts` (los conceptos se copian al buscar);
    - `articles` (una por URL canónica) y `article_texts` (solo para procesar, se borra a los 30 días);
    - `article_concepts`, `article_locations` (el punto sale del catálogo, nunca de la IA) y `search_results`;
    - `processing_errors`.
  - Duplicados: URL canónica sin rastreo, `www.` ni AMP, y títulos casi iguales (≥ 0.9 con rapidfuzz, ±1 día).
  - Extracción del texto con trafilatura. Si falla, se usa título + fragmento (`fallback`).
  - IA detrás de `LLMPort`, con prompt versionado (`enrich_v1`) y respuesta validada con un reintento:
    - OpenAI (`gpt-6-luna`, por defecto; ADR-0016) o Gemini (`gemini-2.5-flash`), elegible con `LLM_PROVIDER`;
    - costo estimado antes de gastar, tope de 150 notas por búsqueda y tokens y costo registrados (ADR-0015).
  - Geolocalizador de §11:
    - alias (`geodata/aliases.csv`) y desempate por los estados de la nota y la región buscada;
    - si sigue ambiguo, sube al estado o queda sin ubicar;
    - parecidos por trigramas con confianza reducida.
  - `RunSearch`: las 8 etapas de §9 con avance real en `searches.progress`.
    - Un error en una nota no detiene la búsqueda. Si falla más de la mitad, queda `partial`.
    - Las notas ya enriquecidas se reutilizan sin pagar.
  - Tarea de Celery `search.run`. La limpieza diaria también borra los textos vencidos.
  - `make buscar`: muestra créditos y costo máximo, pide "si", corre la búsqueda (en el worker o con `--aqui`) y enseña 5 notas con lugar, precisión y confianza.
  - `make reubicar`: vuelve a ubicar las notas de una búsqueda con las reglas y el catálogo vigentes sin pagar a la IA; con `--con-ia` las vuelve a pasar por la IA desde su texto guardado (0 créditos). Las pistas de lugar de la IA se guardan (migración 0014).
  - Globo con rotación automática e inclinación de 15°.

### Corregido

- Geolocalización, con lo aprendido en la primera búsqueda real (Extorsión en Jalisco: 18 notas, 1 crédito y 0.0068 USD):
  - alias de los municipios cuyo nombre oficial es más largo que el de uso diario ("Heroica Ciudad de Juchitán de Zaragoza", "Santo Domingo Tehuantepec"…);
  - una localidad de otro estado ya no se usa si la nota nombra sus estados (la "colonia La Gloria" de Juchitán caía en Guanajuato).

## [0.3.0] - 2026-10-16

### Agregado

- **Fase 3 — Proveedores e ingesta.**
  - Cliente HTTP compartido (httpx2, ADR-0010) con:
    - tiempo máximo por petición;
    - reintentos con espera creciente solo ante 429, 5xx o red caída;
    - espera mínima tras un 429 y User-Agent propio;
    - registro de cada intento fallido.
  - Adaptadores con el mismo contrato (`NewsProviderPort`) y notas en un formato común (`RawArticle`):
    - SearchApi (Google News, la llave viaja en el encabezado);
    - GDELT DOC;
    - Google News RSS.
  - `ExecuteQueries` aplica, en este orden:
    - el presupuesto de 10 consultas por búsqueda;
    - la caché de consultas idénticas (Redis, 6 h);
    - el tope mensual de créditos de SearchApi (100, por mes de la Ciudad de México);
    - el registro de cada petición en `provider_queries` (migración 0007).
  - `make probar-proveedor` (una consulta real con confirmación y fixture sin la llave) y `make gdelt-diagnostico` (reintento diario de D1, ADR-0012).
  - **Índice local de notas** (ADR-0013):
    - tablas `news_index` e `ingest_runs` (migraciones 0008 y 0009);
    - lectura de los archivos GKG de GDELT (solo notas en español con México, verificadas con MD5) y de RSS de medios desde `fuentes/medios_rss.csv`;
    - equivalencias de estados FIPS→INEGI (`geodata/fips_inegi.csv`).
  - Ingesta automática cada 15 minutos con el reloj de Celery (`celery beat`), que arranca `make up`, más limpieza diaria por retención (90 días). `make ingesta` corre una vez y muestra 5 ejemplos.
  - Proveedor `indice_local`:
    - palabra clave completa (sin acentos, con Ñ), exclusiones y lugar en el texto, o la pista de GDELT si la región es un estado;
    - días en hora de la Ciudad de México;
    - gratis y sin caché.
  - `make ingesta-historial DIAS=N`: vista previa del tamaño sin descargar y 5 ejemplos reales; solo baja todo con `DESCARGAR=si`.
  - **Ngramas de GDELT** (ADR-0014): notas en español que mencionan México, con frases del texto completo (`body_terms`, migración 0010) solo para buscar y conservadas 30 días. `indice_local` busca también en el cuerpo. `make ngramas-muestra` prueba una hora real.
  - Pestaña **Notas** (vista temporal hasta F6) y endpoints temporales `/api/v1/local-index/search` y `/stats`.
  - Primera consulta real a SearchApi (1 crédito): 10 notas normalizadas; confirma `iso_date`, `link=resolved` y `time_period`. También quedó grabada la primera respuesta de GDELT DOC con notas.
  - Globo: gira solo (una vuelta cada 90 s, se detiene al tocarlo) con el eje inclinado 15°, como un globo de escritorio. Se endereza al acercarse a una región.
  - ADR-0010 a ADR-0014.

### Cambiado

- Especificación v1.8: F3 pasa a ser "Proveedores e ingesta".
- `PlannedQuery` lleva exclusiones y lugar por separado, y `PlaceFacts`/`QueryPlace` la clave INEGI del estado.
- "Probar concepto" muestra también la consulta del índice local, escrita en palabras.
- El worker y el reloj de Celery escriben logs JSON, igual que la API.
- Especificación v1.9: los ngramas de GDELT son la fuente principal del índice local y el GKG (solo títulos) queda apagado por defecto (ADR-0014).
- RSS de medios: La Jornada, El Universal e Infobae México **encendidos** por decisión de Benji (`MEDIA_RSS_ENABLED=true`); cada medio se apaga en `fuentes/medios_rss.csv`.

### Corregido

- GDELT repetía la misma ubicación por cada mención; ahora se guarda una vez.
- El índice local ya no acepta notas solo porque GDELT las ubicó en el estado buscado: en datos reales metía notas de otros estados (ADR-0014).
- El tamaño y el MD5 de los archivos de GDELT se leen de `x-goog-hash` y `x-goog-stored-content-length`: Google quita el ETag cuando recomprime al vuelo.

### Desactivado

- Google News RSS fuera de producción por sus términos de uso (ADR-0011, `NEWS_RSS_ENABLED=false`).
- API DOC de GDELT apagada mientras responda 429 (ADR-0012, `GDELT_ENABLED=false`); sus archivos sí se usan en el índice local.

## [0.2.0] - 2026-10-16

### Agregado

- **Fase 2 — Conceptos.**
  - Tabla `concepts` (migración 0005) con nombre único sin importar mayúsculas ni acentos, borrado lógico y validaciones:
    - al menos una palabra clave;
    - sin palabras repetidas;
    - ninguna exclusión igual a una palabra clave;
    - sin caracteres que los buscadores toman como órdenes;
    - color `#RRGGBB`.
  - Bitácora de auditoría `audit_log` (migración 0006): cada alta, edición y borrado de un concepto queda con usuario, IP, antes y después, en la misma transacción que el cambio.
  - Constructor de consultas `build_queries` con un dialecto por proveedor (SearchApi, Google News RSS y GDELT), probado con los casos de §7.2:
    - términos de búsqueda curados por lugar (`geodata/search_terms.csv`, migración 0004);
    - el estado cuando un municipio tiene nombre repetido;
    - filtros por país con ISO-2 y FIPS de Natural Earth.
  - Endpoints `/api/v1/concepts`: listar por cursor, detalle, crear, editar, borrar y "Probar concepto" para un concepto guardado o para un borrador sin guardar.
  - `make seed` con los 5 conceptos semilla y `make geo-terms` para aplicar términos de búsqueda y códigos de país sin recargar el catálogo.
  - Pantalla **Conceptos**: tabla con interruptor de activo, formulario con palabras como "chips" y errores por campo, y "Probar concepto" con las consultas exactas por proveedor.
  - ADR-0009 (construcción de consultas).

### Cambiado

- Especificación v1.4: `search_terms` y códigos de país en `regions`, exclusiones también en GDELT, `name_norm` y `deleted_at` en `concepts`, `POST /concepts/preview`.
- Frontend: cliente HTTP compartido (`services/http.ts`) con soporte de POST, PATCH, DELETE y detalles de error.

### Corregido

- `Makefile`: un `\n` literal en la lista `.PHONY`.

### Pendiente

- `is_used_in_searches` responde "no" hasta que F4 cree `search_concepts`; hasta entonces borrar un concepto siempre es físico.
- Límites de largo y operadores no documentados de los proveedores (`when:`, varios bloques OR en GDELT), marcados `VERIFICAR` para F3.

## [0.1.0] - 2026-10-16

### Agregado

- **Fase 1 — Geodatos.**
  - Tabla `regions` (migraciones 0002 y 0003) con 258 países, 32 estados, 2,478 municipios y 296,850 localidades de INEGI (Marco Geoestadístico, Encuesta Intercensal 2025) y Natural Earth.
  - Pipeline `make geo-download`, `geo-inspect`, `geo-load`, `geo-validate`, `geo-tiles` y `geo-basemap`:
    - descarga por HTTP Range solo del marco integrado de INEGI, con manifiesto y SHA-256;
    - detección de encoding con los bytes crudos;
    - carga idempotente con reparación de geometrías;
    - los 11 criterios de aceptación de §12;
    - PMTiles por capa y mapa base de Protomaps autoalojado (mundo z6, México z14).
  - Normalización de nombres que conserva la Ñ, compartida por el cargador y el buscador.
  - Endpoints `/api/v1/regions`: listas por nivel, detalle con migas de pan, hijas, búsqueda por nombre o alias y región en un punto. Paginación por cursor y formato uniforme de errores en español.
  - Explorador de geodatos: globo 3D con MapLibre v6, buscador con autocompletado, tooltip, tarjeta con migas de pan y vuelo a la región.
  - `make db-shell`, `make db-dump` y guía para consultar y migrar la base (`docs/base-de-datos.md`).
  - ADR-0007 (MapLibre v6) y ADR-0008 (fuentes y procesamiento de geodatos).

### Cambiado

- Especificación v1.3: MapLibre GL JS v6 y lógica del pipeline en `backend/app/geodata/`.
- nginx: tipos correctos para sprite, fuentes y el worker `.mjs` de MapLibre; `index.html` sin caché; la CSP ya no permite `blob:` en `worker-src`.

### Corregido

- GDAL ya no lee directamente de `/mnt/d`, donde recibió bytes dañados en WSL. Ahora se extrae con verificación de CRC al disco de Linux.

## [0.0.0] - 2026-10-15

### Agregado

- **Fase 0 — Cimientos.**
  - Entorno de desarrollo sin Docker, con los servicios nativos en Ubuntu dentro de WSL (ADR-0006). `make bootstrap` instala PostgreSQL 16 + PostGIS 3.6, Redis 8, nginx, uv y Python 3.12 con un script que se puede repetir.
  - Comandos `make up`, `down`, `status`, `logs`, `test`, `lint`, `format`, `migrate` y `frontend-build`.
  - Endpoint `GET /api/v1/health` con el estado de la API, la base de datos (versión y extensiones), Redis y el worker. Responde 200 si todo está bien y 503 si algo falla, con el detalle en español.
  - Página inicial "Estado del sistema" con semáforo por componente, actualizada cada 10 segundos.
  - Backend FastAPI con arquitectura hexagonal, configuración por variables de entorno, logs JSON, Alembic (migración inicial de extensiones) y worker Celery.
  - Frontend React 18 + TypeScript + Vite + Tailwind CSS v4, con ESLint, Prettier y Vitest.
  - nginx como punto de entrada único (<http://localhost:8080>): frontend, proxy a la API, teselas con Range y encabezados de seguridad.
  - `.gitattributes` que fuerza finales de línea LF (CRLF solo en scripts de Windows), `.editorconfig` y pre-commit.
  - ADRs 0001 a 0006, README de arranque desde cero y documentación de arquitectura.

### Cambiado

- Especificación v1.2: campo `aliases` en `regions`, filtro `sourcecountry` en GDELT, nota sobre los links de Google News RSS y entorno de desarrollo sin Docker.
