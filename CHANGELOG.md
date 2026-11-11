# Historial de cambios

Todos los cambios importantes de este proyecto se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [versionado semántico](https://semver.org/lang/es/): cada fase N cierra con la versión `v0.N.0`.

## [Sin publicar]

### Agregado

- **Radar sobre la zona buscada (11/11/2026).** Mientras corre una búsqueda:
  - el radar se centra en la región y toma su tamaño;
  - marca la región con esquinas de «objetivo» y sus coordenadas;
  - enciende un símbolo de nota por cada nota encontrada y muestra la etapa en curso.

- **Código opcional y llave de API por persona (11/11/2026, ADR-0047, migración 0044).** Benji: «dice mi jefe que es tedioso» y «cada usuario debe tener su propia API key».
  - En «Accesos», el interruptor **Pedir código de Microsoft Authenticator al entrar**. Arranca apagado: se entra con usuario y contraseña.
  - Cada persona tiene su **llave de API**, que el superusuario puede ver, copiar o cambiar. Se guarda cifrada y cada vista queda en la bitácora. Los usuarios normales no la ven.
  - Guía para conectar otro sistema: `docs/guia-integracion-api.md`.

- **Envíos totalmente personalizables (11/11/2026, ADR-0046, migración 0043).** Benji: «que los envíos sean totalmente moldeables y personalizables», para los usuarios y para él.
  - Cada persona programa sus envíos: qué temas, de dónde (país, estado o municipio), a qué horas (las que quiera, al minuto), qué días y a cuáles de sus correos.
  - Tope de 3 corridas al día por usuario y 8 para el superusuario.
  - Los envíos que piden lo mismo a la misma hora comparten una sola corrida con IA.
  - El horario único de la FGR pasó a ser el envío «Monitor FGR» de Benji. Cada usuario, nuevo o existente, empieza con su copia: solo agrega su correo.
  - Ya no se muestra desde qué correo se envía.
  - `make corrida-fgr` ya no manda correos; eso lo hacen los envíos programados.

- **Envíos por usuario (11/11/2026, ADR-0045, migración 0042).** Benji: «que ellos agreguen su correo y ya les van a estar empezando a llegar las noticias».
  - Cada usuario agrega hasta 2 correos en «Mis envíos».
  - El correo que envía lo decide el superusuario.
  - Cada persona ve solo sus correos y su historial: lo cuida la base (seguridad por filas). El superusuario ve todo, con el dueño de cada correo.
  - Lo que ya existía queda a nombre de Benji y sigue igual.

### Cambiado

- **Fechas y zonas estrictas (11/11/2026, ADR-0048).** Benji: «si le doy buscar hoy, solo hoy».
  - Una búsqueda manual solo guarda lo publicado en los días pedidos, de 00:00 a 23:59 de la Ciudad de México.
  - En un estado o municipio, una nota sin lugar ya no cuenta como de la zona.
- **Globo:**
  - se quitaron «Pausar giro» y la velocidad de la animación; la animación siempre es lenta;
  - gira en una consulta nueva o tras 5 minutos sin tocar nada, y se detiene al volver.
- **Relevancia mucho más estricta (11/11/2026, ADR-0044).** Benji: «me está arrojando información basura».
  - La IA (`enrich_v4`) solo marca una nota como relevante si el tema es **el asunto principal**. Ya no cuentan las agendas de marchas, los resúmenes del día ni las menciones de pasada.
  - Sí cuentan el activismo de víctimas y colectivos, y las acciones oficiales de una institución como la FGR.
  - Un «sí» de la IA con menos de 60 % de confianza ya no cuenta. Esto también aplica a las búsquedas pasadas.
  - **Prueba real:** de 14 notas «relevantes» de una búsqueda quedaron 5, todas correctas, y se quitaron 8 notas basura.

### Corregido

- Las notas con muchos lugares (agendas) ya no se quedan sin resumen por una respuesta cortada de la IA (2 de 25 en la prueba).
- «Copiar contraseña», «Copiar llave» y «Copiar consulta» funcionan también por `http://`.
- El letrero de una nota ya no queda encimado con la ventana «N notas en este lugar».
- Las etapas «Mapa» y «Región» ahora se llaman «Ubicar» y «Zona».

### Agregado

- Al volver al monitor desde otro módulo de Oráculo, se retoma la búsqueda abierta en la etapa en que va.

- **Se entra al monitor igual que a Oráculo: usuario, contraseña y código de 6 dígitos (10/11/2026, ADR-0043, migración 0040).** Benji: «que puedas acceder con contraseña, y esa contraseña genere un token interno que sea su identificación para los demás módulos».
  - **Primer ingreso:** contraseña temporal que da el administrador → contraseña propia (12+ caracteres, letras y números) → escanear un QR con Microsoft Authenticator.
  - **Los demás días:** usuario, contraseña y código. La sesión dura hasta «Salir» (máximo 30 días).
  - **Token interno:** la sesión vive en una cookie que el JavaScript no puede leer. Otros módulos de Oráculo pueden preguntar de quién es con `POST /api/v1/auth/introspect`, sin pedir contraseña.
  - **Seguridad:**
    - contraseñas con huella scrypt;
    - secreto del código cifrado con AES-256-GCM;
    - ningún código sirve dos veces;
    - 5 fallos bloquean la cuenta 15 min y 10 fallos por IP bloquean la IP;
    - el mismo mensaje para usuario inexistente o contraseña equivocada.
  - **«Accesos»:**
    - dar de alta con contraseña temporal (se ve una sola vez);
    - «Restablecer contraseña» y «Reiniciar autenticador»;
    - etiquetas «Contraseña temporal», «Sin Authenticator» y «Bloqueada».
  - **Cada quien:** botón «Mi contraseña» para cambiar la suya.
  - **Borrar personas** desde «Accesos» (borrado lógico, migración 0041): ya no entran y su usuario queda reservado; sus búsquedas y la bitácora se quedan.
  - **Llaves `orc_live_…`:** quedan solo para sistemas.
  - **Nuevo comando:** `make acceso` da una contraseña temporal desde la consola del servidor.
  - **Dependencias:**
    - `segno`, nueva, dibuja el QR;
    - `cryptography`, ya estaba instalada y ahora se declara.

- **Acceso con llave, usuarios y roles; cada quien su historial (10/11/2026, ADR-0042, migraciones 0038 y 0039).** Benji: «un token como el de la API de ChatGPT», seguridad altísima, y que cada usuario tenga su propio historial con RLS. Es la etapa 1 de 3.
  - **Entrar con llave `orc_live_…`.** La pantalla pide la llave una vez y abre una sesión con cookie `HttpOnly` de hasta 8 h, que se cierra tras 1 h sin uso. Otros sistemas mandan la llave en `Authorization: Bearer`. La base guarda solo una huella con «pimienta», nunca la llave.
  - **Roles.** El superusuario (Benji) ve todo, más «Estado del sistema» y la nueva pestaña **«Accesos»**. El usuario normal ve Explorar, Casos, Conceptos e Historial; cada ruta revisa el rol, no solo la pantalla.
  - **«Accesos».** Dar de alta personas, cambiar nombre, correo y rol, desactivar, y crear o revocar llaves. La llave nueva se muestra una sola vez, con botón para copiarla.
  - **Cada quien su historial, con seguridad por filas (RLS) en PostgreSQL.** Una búsqueda ajena no existe para la base: responde 404 aunque se pida por su id. El superusuario tiene «Ver de todos».
  - **Protecciones:**
    - freno de 10 intentos fallidos por IP;
    - revisión contra peticiones de otros sitios (CSRF);
    - revocar o desactivar saca al instante;
    - nadie se quita su propio rol;
    - siempre queda un superusuario.
  - **Todo lo de Benji sigue igual.** Lo que era de «desarrollo» pasó a `benji`; las corridas 07:00, 15:00 y 23:00 y sus correos no cambian.
  - **Nuevo comando** `make crear-llave` para la primera llave y para recuperar el acceso.

- **Ajustes de búsqueda pedidos por Benji (09/11/2026).**
  - **Las notas fuera de la región ya no cuentan (ADR-0041).** Una búsqueda de «PDI» en México traía 47 notas de Chile: «PDI» es la policía chilena. Ahora lo de fuera no sale en la lista, el globo, los conteos, el PDF ni los correos, y una nota sin lugar de un medio de otro país (`.cl`, `.pe`…) también cuenta como fuera. Se puede revisar con el filtro «fuera de la región».
  - **«Todo México» se puede elegir sin moverle.** Al abrir «Dónde» ya queda elegido de verdad. Antes solo lo parecía y no dejaba barrer.
  - **Botón «← Oráculo»** en el encabezado, para regresar al sistema principal (`ORACULO_URL`).
  - **Subdivisiones editables al 100%.** En «Conceptos → Subdivisiones» se agregan (con las palabras de su tema general) y se borran (sus notas pasan a «Otros»; «Otros» no se borra).
  - **«¿Qué rastrear?» con una sola lista de delitos.** Antes «Homicidio» salía dos veces. Ahora se elige **con quién** (FGR, Policía de investigación o «Con nadie en particular») y **qué delitos**, cada uno una sola vez, y una frase dice qué va a traer la búsqueda («Notas de la FGR que además hablan de Homicidio»).

- **La base del monitor vive en el PostgreSQL general de Oráculo (07/11/2026).** Benji: «actualmente sí se están respaldando nuestras bases de datos».
  - Base `monitor_noticias` en `192.168.0.20` (PostgreSQL 17.9), con su propio usuario sin permisos de administrador. Entra en los respaldos del servidor general y se ve en DBeaver junto a las demás bases.
  - El monitor sigue corriendo en la VM 108. Se copió con 0 errores y los mismos conteos, y la base anterior queda de reserva en la VM.

- **El monitor corre en la VM de Proxmox (07/11/2026, docs/migracion-proxmox.md).** Ya no depende de que la PC de Benji esté prendida.
  - VM 108 «noticias» (Ubuntu 24.04). El equipo la abre por ZeroTier en `http://10.244.214.144:8080`.
  - Arranca sola al encender (servicio `monitor-noticias`). Hace las corridas de las 07:00, 15:00 y 23:00 y manda los correos; la PC quedó solo para desarrollar.
  - Los scripts ahora sirven en un Linux sin Windows: `make bootstrap` instala Node 22, `NGINX_LISTEN` y `API_RELOAD` ajustan el servidor, y `make instalar-servicio` registra el arranque y permisos mínimos de administrador.

- **Horario único de las corridas, editable desde «Envíos» (06/11/2026, ADR-0040, migración 0037).** Benji: «si nosotros editamos, borramos o añadimos algún horario, tiene que funcionar para todos los usuarios».
  - En **Envíos → Horario de las corridas** se agregan, quitan o mueven horas y días. Aplica en el minuto siguiente, sin reiniciar nada, y cada cambio queda en la bitácora.
  - **A cada hora se hace un reporte totalmente nuevo** con lo publicado desde la hora anterior. Si se agregan las 19:00, esa corrida cubre de 15:00 a 19:00 y la de las 23:00 pasa a cubrir de 19:00 a 23:00.
  - **Topes contra el consumo de tokens:** máximo 8 horas al día y 60 minutos entre una y otra. La pantalla avisa cuánto cuesta cada hora extra (≈ US$0.04 por corrida).
  - El reporte de cada corrida va a **todos** los destinatarios con «Recibe envíos» prendido. Se quitaron las reglas personalizadas y el reenvío del último reporte a horas sin corrida.
  - El Centro de mando muestra la próxima corrida del horario guardado.

- **Envíos: regla general y horas libres (07/11/2026, ADR-0039, migración 0036).** Benji pidió una regla general en lugar de una regla por persona, y más opciones.
  - **Regla general:** el reporte a todos los destinatarios activos, con excepciones («todos menos Tadeo»).
  - **Horas y días a elegir:** cualquier hora, no solo las de las corridas. Las horas se agregan o se quitan con un clic, y los días van de lunes a domingo, con atajos «Lunes a viernes» y «Todos». A una hora sin corrida se manda el reporte más reciente.
  - **Reglas personalizadas** para unas cuantas personas, como tarjetas que se despliegan para editar. Al lado, la lista de **próximos envíos**.
  - **Destinatarios:** «Editar» despliega el perfil ahí mismo y «+ Agregar» abre una ventana. Ya se pueden borrar destinatarios y reglas.
- **Sección «Envíos» (07/11/2026, ADR-0039).** Benji pidió administrar qué se manda, a quién, por qué canal y a qué hora.
  - **Cuentas de envío:** se conecta Outlook, Hotmail o Gmail con un link de autorización (Composio). WhatsApp aparece como «Próximamente».
  - **Destinatarios y reglas:** por ejemplo, «Reporte FGR → Benjamin → por correo desde Ovitech → 07:00 y 15:00».
  - **Historial:** cada envío con estado, intentos y error en español, y los botones «Reintentar» y «Mandar prueba».
  - Al terminar cada corrida se mandan los envíos de las reglas que tocan, con el PDF adjunto. Se reintenta a los 1, 5 y 30 minutos y nunca se manda dos veces lo mismo.
  - Apagado por defecto: `DELIVERIES_ENABLED=false`. Pensado para volverse el módulo de envíos de todo Oráculo.
- **Subdivisiones editables y temas generales (02/11/2026, ADR-0038).** Benji pidió ver y editar todas las subdivisiones, no solo las 8 que salían en las notas, y poder buscar «solo homicidios en general, sin la FGR».
  - Cada subdivisión, menos «Otros», tiene su **tema general**: un concepto con palabras clave que se busca solo. `make seed` siembra los 14 desde `temas.json`.
  - **FGR · Homicidio** trae solo notas con **ambas** palabras: la consulta lleva un segundo grupo con las palabras del tema (`category_ids` en `POST /searches`). La palabra del tema tiene que estar en el título o el resumen, no perdida en el cuerpo. En una semana real, eso bajó «FGR · Homicidio» de 145 a 39 notas, todas de homicidios.
  - En el Centro de mando, «Qué rastrear» abre una ventana al centro con dos bloques: la FGR con sus subdivisiones («Todas» o las que elijas) y los temas generales. La frase dice, por ejemplo, «FGR · Homicidio». Los bloques no se mezclan: elegir un tema general apaga la FGR, y al revés, para que la FGR nunca se sume a todos los homicidios.
  - En «Conceptos», el panel **Subdivisiones** muestra las 15, también las apagadas. Cada una se edita con su nombre, color, lo que lee la IA, si está prendida y las palabras de su tema.
  - `PATCH /categories/{id}` cambia nombre, descripción, color y si está prendida, con bitácora. `GET /categories?include_inactive=true` trae también las apagadas.
  - La corrida automática no cambia, y `make retirar-conceptos` ya no retira los temas.
- **PDF más visual y sin listados interminables (28/10/2026, ADR-0033).** Benji: «prefiero resúmenes, gráficas, datos importantes». El reporte trae:
  - una dona por delito;
  - la línea del tiempo por hora de colores por categoría, como el globo;
  - una cronología de los 8 hechos que más medios publicaron, con su resumen;
  - un índice compacto, un renglón por hecho y hasta 40 hechos; lo demás se consulta en el monitor o en el CSV.

  La portada, el panorama, el mapa y el anexo siguen igual.
- **Calendario con el estilo del sistema (28/10/2026, `HudDatePicker`).** «Desde» y «Hasta» ya no abren el calendario gris del navegador. Ahora el calendario es propio:
  - vidrio oscuro y días que se iluminan al pasar el mouse;
  - hoy con un punto, el día elegido brillando y una banda entre las dos fechas;
  - el mes cambia deslizándose;
  - no deja elegir días después de hoy, ni un «hasta» antes del «desde».

  Se usa con el mouse o con el teclado.
- **Consola del Centro de mando en tres zonas, sin textos cortados (28/10/2026).** Antes, «Abrir resultados anteriores» se encimaba con el costo, y había textos a medias: «CENTRO DE MAND…», «CONSU…», «Tu búsqueda del 27…». Ahora:
  - arriba, a todo el ancho, el título completo, la próxima corrida y el reloj;
  - en medio:
    - un radar grande, cian mientras se arma la consulta y verde cuando ya se puede lanzar;
    - la frase;
    - el costo en renglones con su nombre completo (consultas, créditos, IA máximo) y «Iniciar barrido», que respira cuando está lista;
  - abajo, a todo el ancho, la última corrida y las dos búsquedas más recientes, completas.

  La fuente de la frase dice solo «Fuente»; el detalle sale al pasar el mouse.

- **«Filtro» en una ventana al centro de la pantalla (28/10/2026).** Un solo botón «Filtro» abre la ventana, sobre un fondo oscuro, para filtrar por:
  - categoría: cuadros de color en una cuadrícula ordenada, una o varias;
  - estado: lista desplegable;
  - ubicación: dentro, fuera o sin lugar;
  - no relevantes.

  El botón dice cuántos filtros hay puestos, y lo elegido vale para la cronología, la lista y el globo. Las pestañas de ubicación de la lista y la línea del tiempo de arriba se quitaron para dejarle el espacio a las noticias.
- **Cada tipo de noticia tiene su color (28/10/2026, migración 0032).** Las 15 categorías tienen un color propio, el mismo en la barra del expediente, las etiquetas de la lista y de la cronología, los nodos de la cronología y los puntos del globo. Ejemplos: Homicidio en rojo, Huachicol en verde lima, Secuestro en rosa y Otros en gris. Solo se llenan los colores vacíos; si alguien elige uno, se respeta.
- **Diseño 3, «Centro de mando», para comparar (27/10/2026, ADR-0037).** Se abre con `?mando#/explorar`; sin `?mando` sigue el diseño 2, igual que antes. Usa el mismo globo, los mismos estilos y los mismos botones, con otro acomodo de la búsqueda:
  - **la búsqueda se lee como una orden:** «Rastrear [FGR] en [Jalisco] durante [los últimos 7 días] vía [2 fuentes gratis]». Cada parte se toca para cambiarla y las que faltan brillan en ámbar;
  - **«Iniciar barrido»:** botón con aro de carga y onda expansiva; antes de lanzar, el costo se ve con cifras que corren;
  - **mientras busca:** un radar barre el globo, un riel enciende las 8 etapas, corren el porcentaje y el cronómetro, y una bitácora dice lo que ya se sabe;
  - **al terminar:** el letrero «BARRIDO COMPLETO» y un expediente a la derecha con relevantes, estados, créditos, costo de la IA, las categorías que más salen, y la cronología o la lista;
  - **el globo:** flota entre el encabezado y la consola, siempre completo, y se corre a la izquierda con el expediente;
  - **personalizada:** las misiones recientes y la última corrida automática se reabren sin costo; hay un reloj de la Ciudad de México con la cuenta regresiva a la próxima corrida automática, y el atajo «/» abre la región.
- **El globo se acomoda a la búsqueda (27/10/2026).** En Explorar, con la columna de búsqueda a la vista, el mundo se corre a la parte libre de la derecha. Al ocultarla (o al ocultar el panel), se desliza al centro y crece un poco sin dejar de girar. Al volver a abrirla, regresa. Los vuelos a un estado o municipio encuadran la región en la parte libre. En celular la columna tapa todo y el globo se queda centrado.
- **Diseño «consola táctica» en todo el monitor (27/10/2026, ADR-0036).** El jefe de Benji vio la interfaz genérica y sin animación. Ahora Explorar, Casos, Conceptos, Historial y Estado del sistema usan las mismas piezas:
  - **paneles:** borde de luz y halo que siguen al mouse, y esquinas de mira;
  - **botones:** destello, onda al hacer clic y texto que se abre al pasar el mouse;
  - **animaciones:** insignias con pulso de radar, cifras que corren, títulos y pestañas que se descifran;
  - **selectores e interruptores:** pastilla deslizante e interruptores con brillo;
  - **filas de lista:** se iluminan con una barra de luz;
  - **cada pantalla:**
    - Estado del sistema: latido por servicio;
    - Historial: radar en las corridas automáticas;
    - campos: aro de enfoque;
    - aviso «Deshacer»: barra de tiempo.

  La muestra de todas las piezas sigue en `?diseno#/diseno`.
- **Menús desplegables con el estilo del sistema (27/10/2026).** Los 9 menús (estado, municipio, localidad, filtros de la cronología, animación del globo, sensibilidad del caso, estatus legal, unir entidades y tipo de vínculo) ya no usan la lista del navegador. Ahora:
  - se despliegan con animación;
  - la opción bajo el mouse o el teclado se ilumina con una barra de luz, y la elegida lleva palomita;
  - se manejan con flechas, Enter, Escape o escribiendo la primera letra.
- **El PDF de cada corrida automática trae solo hechos nuevos (27/10/2026, ADR-0034).** Cada corrida cubre hoy y ayer, así que entre el 66 y el 94 % de sus notas ya venía en la anterior. El reporte ahora se compara con la última corrida automática terminada:
  - «Noticias por estado» lista solo los hechos que no traía esa corrida;
  - en la página 2, «Novedades» dice cuántos hechos son nuevos y cuántos no se repiten;
  - el panorama, las gráficas y el mapa siguen cubriendo toda la ventana.

  En la corrida de las 23:00 del 26/10 fueron 33 hechos nuevos y 65 que no se repiten. El PDF bajó de 26 a 14 páginas. La auditoría completa está en `docs/analisis-2026-10-27.md`.
- **Eliminar casos y búsquedas del historial (27/10/2026).** Se borran de forma reversible:
  - el primer clic pide confirmar («¿Eliminar? · Sí, eliminar · Cancelar») y luego aparece un aviso con «Deshacer» durante 8 segundos;
  - un caso solo lo elimina su dueño; del historial se pueden quitar las búsquedas propias y las corridas automáticas;
  - la fila se queda en la base con `deleted_at` y `deleted_by` (migración 0030), así que las notas, las entidades y la bitácora no se pierden; cada eliminación y cada restauración queda en la auditoría;
  - rutas nuevas: `DELETE /cases/{id}`, `POST /cases/{id}/restore`, `DELETE /searches/{id}` y `POST /searches/{id}/restore` (`docs/api.md`).
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

- **Encabezado con luz de neón (02/11/2026).** El nombre del monitor brilla como letrero de neón: se enciende parpadeando al cargar y luego respira. Las pestañas también brillan, más la elegida.
- **El PDF pregunta «¿Qué cambió desde la corrida anterior?» (02/11/2026, ADR-0033).** En lugar de «¿Qué tipo de actuación hubo?», compara la corrida con la anterior:
  - el total de antes y el de ahora;
  - los delitos y los estados que más subieron o bajaron;
  - los focos nuevos y los estados que se quedaron sin notas.
- **PDF en Barlow (02/11/2026).** Benji la eligió entre tres muestras: Barlow Semi Condensed en títulos y cifras, y Barlow en el texto. Las flechas se dibujan para no depender de fuentes del sistema.
- **Letra más moderna en la interfaz y en el PDF (30/10/2026).** Títulos, botones, etiquetas y cifras van en Exo 2, técnica pero sobria, y el texto en Inter. Orbitron queda solo en el logo. El PDF usa la misma pareja, en lugar de IBM Plex, para que se vea del mismo sistema.
- **El globo gira solo mientras no se ve nada en particular (30/10/2026).** En el Centro de mando, con los resultados a la vista, el globo vuelve a girar a los 10 segundos sin uso. Se detiene al abrir una nota, el muro o la lista de un grupo.
- **PDF en IBM Plex (30/10/2026).** La tipografía ya no parece de procesador de textos:
  - IBM Plex Sans en el texto, justificado;
  - IBM Plex Sans Condensed en títulos, titulares y cifras;
  - IBM Plex Mono en horas y número de expediente.

  Reemplaza a Noto Serif.
- **PDF con tipografía formal y texto justificado (30/10/2026).** Se cambió la tipografía:
  - el texto de lectura (resumen ejecutivo, resúmenes de los hechos, metodología) va en Noto Serif, justificado y con división de palabras en español;
  - los titulares de las notas y el título de la portada, en Noto Serif negrita;
  - las preguntas, los títulos, las cifras y las etiquetas, en Noto Sans seminegrita;
  - las conclusiones de cada pregunta, en cursiva.

  Las fuentes van incluidas en el repositorio con su manifiesto y su SHA-256.
- **Las corridas dejan fuera los hechos de otros días, no las sentencias de hoy (28/10/2026, `enrich_v3`, ADR-0031).** La IA ahora da la fecha y el tipo de lo que la nota informa (la detención, la sentencia, el cateo) en lugar de la fecha del delito original. Con esa fecha, cada corrida quita las notas cuyo hecho es de antes de su periodo: el cateo de ayer publicado hoy sale; la sentencia de hoy por un delito de 2019 se queda. La cronología también acomoda cada nota en la fecha de lo que informa.
- **«Nueva consulta» y «Ajustar consulta» regresan el globo al Atlántico y lo ponen a girar (28/10/2026).** Al tocar cualquiera de los dos botones, el globo vuela a la vista del Atlántico, la misma con la que abre el sistema, y al llegar empieza a girar solo. «Limpiar globo», en el diseño de columna, sigue volviendo a México.
- **La espera del barrido, más viva y más clara (28/10/2026).** Mientras se busca:
  - una ráfaga de luz corre por las etapas ya hechas;
  - la etapa en curso tiene un aro que gira;
  - las terminadas se encienden con una palomita;
  - las que faltan laten en ola;
  - la bitácora escribe con cursor y una franja de escaneo recorre la consola.

  La bitácora ya no dice «Fuentes consultadas: 512 notas», que parecía 512 resultados. Dice «Notas encontradas: 512 (la IA decide cuáles sirven)» e «IA leyendo: 110 de 295 nuevas · 217 ya leídas antes».
- **El PDF responde las preguntas del analista (28/10/2026, ADR-0033).** Cada bloque abre con una pregunta numerada, su gráfica y una línea de conclusión:
  - ¿Qué pasó?
  - ¿Qué es lo más importante?
  - ¿De qué delitos se trata?
  - ¿Qué tipo de actuación hubo?
  - ¿Dónde pasó?
  - ¿Qué pasa en cada estado?
  - ¿Cuándo pasó?
  - ¿Cómo se desarrollaron los hechos?
  - ¿Qué tan confiable es?

  También hay novedades de presentación:
  - una cronología con marcas de hora;
  - fichas por estado;
  - un índice por estado con franjas de color;
  - tipografía formal: Noto Sans en lugar de Orbitron, que solo queda en la marca de la portada.
- **Consola más chaparrita y ubicación sin ambigüedad (28/10/2026).**
  - La consola del Centro de mando baja de 240 a 179 px de alto con las mismas piezas: el radar, la frase y los márgenes son más chicos, y el costo va en un solo renglón de tres cifras con su nombre completo.
  - En el filtro de ubicación, «Dentro» y «Fuera» ahora dicen «Dentro de zona» y «Fuera de zona», también en el diseño de columna.
- **Cada corrida automática trae solo lo publicado desde la anterior (28/10/2026, ADR-0031, migración 0033).** La de las 07:00 cubre de las 23:00 de ayer a las 07:00, la de las 15:00 de 07:00 a 15:00 y la de las 23:00 de 15:00 a 23:00. Antes pedía «hoy y ayer» y la de las 07:00 del 28/10 trajo 356 notas: 160 relevantes, de las que solo 23 eran nuevas. Con la ventana habrían sido 73 notas y 22 relevantes. Lo de fuera ni se guarda ni se paga a la IA. La pantalla y el PDF dicen las horas que cubre cada corrida.
- **En el expediente, sin la curva de notas por hora; los atajos de la consola se entienden mejor (28/10/2026).** Las corridas dicen sus horas y las búsquedas anteriores, su día: «Tu búsqueda del 27 oct: FGR en Jalisco».
- **El expediente muestra muchas más noticias (28/10/2026).** En una pantalla de 900 px de alto caben 9 a 11, antes 2 o 3. Cambios:
  - las pestañas «Cronología | Noticias» están dentro del panel de noticias, en el mismo lugar para las dos vistas;
  - el resumen es más bajo y el PDF es un botón chico junto al título;
  - cada renglón muestra el título en una línea; al elegirlo o al pasar el mouse se ve completo;
  - en cada renglón, el medio, el lugar, la categoría y «+N» van en un solo renglón de datos.
- **Vista general más grande al abrir el sistema (27/10/2026).** En el Centro de mando, de la consola de abajo solo se reserva un 35 % de su alto: el globo crece y su orilla pasa por detrás del vidrio, como pidió Benji. Al volar a una región o a una noticia se usa el margen completo, para que nada quede tapado.
- **El globo abre más grande y los vuelos a una noticia son más ágiles (27/10/2026).** Benji lo pidió. El zoom inicial pasa de 1.8 a 2, y en el Centro de mando el globo ocupa todo el alto entre el encabezado y la consola. Volar a una noticia tarda 25 % menos y hace más arco. La ficha queda debajo de los controles del globo.
- **Las corridas automáticas leen hasta 250 notas nuevas con la IA (27/10/2026, ADR-0031).** Antes era el tope general de 150; en la corrida de las 15:00 se alcanzó y 10 notas esperaron a la siguiente. Cuesta unos 0.025 USD más por corrida en el peor caso. Las búsquedas manuales siguen con 150. Se ajusta con `AUTOMATIC_LLM_MAX_ARTICLES`.
- **Más noticias a la vista en el expediente y una cronología más clara (27/10/2026).** En una pantalla de 920 px de alto pasan de 3 a unas 6 o 7. Cambios:
  - el resumen es más bajo: cifras más chicas, categorías en un renglón, y pestañas y PDF juntos;
  - si se pliega, el resumen se queda plegado en las siguientes visitas;
  - dentro del expediente, la cronología no repite su título y la curva es más baja;
  - la curva dice de qué hora a qué hora va;
  - cada renglón muestra el medio, el lugar, la categoría y cuántos medios lo publicaron como etiquetas, y cada día dice cuántas entradas tiene.
- **«Consulta» en lugar de «misión» en el Centro de mando (27/10/2026).** Por ejemplo: «Consulta activa», «Ajustar consulta» y «Nueva consulta». Benji pidió un término más profesional.
- **El Centro de mando es el diseño principal (27/10/2026, ADR-0037).** Explorar abre con él sin nada en la URL. El diseño de columna sigue con `?clasico#/explorar` y quedó guardado en la etiqueta `diseno-consola-tactica-v2`. Al elegirlo, Benji pidió estos ajustes:
  - **la consola:** más chica, de vidrio translúcido (se ve el globo detrás) y sin naranja; lo que falta elegir late en cian;
  - **el expediente:** más ancho (30 rem), y el resumen de arriba se pliega aparte para que la lista tenga casi todo el alto;
  - **las noticias:** la cronología y la lista se ven 10 % más grandes;
  - **las cifras:** láminas de vidrio de colores, con un brillo que las cruza; la barra de categorías brilla.

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

### Quitado

- **God's Eye View** (27/10/2026, ADR-0035): se probó el mismo día como módulo aparte, con su pestaña «God's Eye». Benji lo retiró porque no le sirve para el monitor, y además era lento y no combinaba con el diseño. Se quitaron la pestaña, el servicio de `make up` y los comandos `gev-*`.

### Corregido

- **Una nota vieja ya no se cuela en la corrida siguiente con otra fecha (28/10/2026).** En la corrida de las 15:00, el índice local volvió a mandar 6 notas de la madrugada con una fecha dentro de la ventana, y salían repetidas de la corrida de las 07:00. Ahora, después de reconocer una nota ya guardada, se vuelve a filtrar con la fecha con la que se guardó. Las 6 se quitaron de esa corrida.
- **Cada corrida trae solo las notas de su periodo, aunque la anterior falle (28/10/2026).** Si una corrida no terminaba, la siguiente cubría desde la última que sí, y podía traer notas de otro periodo. Ahora la ventana es siempre la misma (ADR-0031):
  - la de las 07:00, de las 23:00 a las 07:00;
  - la de las 15:00, de 07:00 a 15:00;
  - la de las 23:00, de 15:00 a 23:00.

  Se quitó `AUTOMATIC_WINDOW_DAYS`.
- **Al elegir un país, el globo se acerca a él (28/10/2026).** En el Centro de mando, el vuelo seguía apartando la columna de búsqueda del diseño 2, que ahí no existe. Por eso Estados Unidos o Argentina quedaban corridos al oeste y más lejos que antes. Ahora el país queda al centro del espacio libre y lo llena, con poco margen.
- **La entrada del globo llega directo a su lugar (28/10/2026).** Al abrir el sistema la Tierra giraba, se detenía y luego se recorría hacia arriba y cambiaba de tamaño, porque terminaba en un zoom fijo y después se reacomodaba al espacio libre. Ahora la entrada calcula desde el principio el zoom y el margen finales y llega ahí sin segundo ajuste.
- **Elegir un país o una región en el Centro de mando ya hace zoom directo a él (27/10/2026).** Antes, al llegar a un país (zoom menor a 3), cualquier cambio de alto de la consola volvía a ajustar el globo entero y lo alejaba. Ahora ese ajuste solo aplica en la vista general, sin región ni nota elegida.
- **El globo siempre llega a la noticia elegida (27/10/2026).** Fallaba en dos casos:
  - si se elegía una nota o se reabría una búsqueda mientras la Tierra hacía su entrada, la entrada seguía moviendo la cámara y aplastaba el vuelo. Ahora cualquier vuelo pedido termina la entrada;
  - al aparecer el expediente a media llegada, el ajuste de márgenes cortaba el vuelo. Ahora espera a que aterrice.
- **Elegir un hecho de la cronología siempre abre su nota en el globo (27/10/2026).** Antes no pasaba nada en dos casos:
  - el hecho se abría con la primera nota publicada, que suele venir de Google News sin texto ni lugar, aunque otro medio del mismo hecho sí dijera dónde pasó. Ahora se abre la nota mejor ubicada del hecho;
  - la nota no tenía lugar (23 de las 161 relevantes de la corrida de las 15:00). Ahora su ficha sale en medio del espacio libre con el aviso «Sin lugar en el mapa», y en la cronología el renglón dice «sin lugar».

- **Las pestañas responden al clic aunque sus letras se estén descifrando** (27/10/2026). Mientras dura la animación, el texto vive en partes internas que se crean al empezar y se borran al terminar. Un clic que empezaba sobre una de ellas y acababa cuando ya no existía se perdía, y había que esperar a que la animación terminara. Esas partes ya no reciben el mouse: el clic cae siempre en la pestaña. Lo mismo para las cifras que corren.
- **El globo deja de cargar la tarjeta de video con desenfoques** (27/10/2026): trece paneles y avisos usaban `backdrop-blur`, que obliga a volver a dibujar lo de atrás cada cuadro. Ahora son paneles oscuros sin desenfoque.
- **La tarjeta de Historial ya no se desarma en pantallas angostas** (27/10/2026): el título se partía en una palabra por renglón.
- **Google News llegaba viejo e incompleto a las corridas (27/10/2026, ADR-0034):**
  - **caché:** las corridas de las 07:00 y de las 15:00 reusaban la respuesta de horas antes (caché de 6 h). Google News es gratis y ya no pasa por la caché;
  - **tope:** cada consulta trae a lo más 100 notas. Ahora se parte por palabra clave y por día, hasta 4 consultas por concepto;
  - **acentos:** «Fiscalia General de la Republica», sin acentos y entre comillas, traía 4 notas en dos días. El concepto ahora busca «Fiscalía General de la República» (migración 0031).

  En la sonda del mismo día, la ventana de dos días juntó 281 notas distintas en lugar de 102. Cuesta unos 0.02 USD más por corrida.
- **El índice local ya no corta en 250 notas** (27/10/2026): la corrida de las 23:00 llegó justo a ese tope. Ahora son 500.
- **La misma nota ya no se guarda dos veces cuando Google News la vuelve a fechar** (27/10/2026): el mismo medio con el mismo título exacto, a menos de una semana, es la misma nota. La regla pide al menos 6 palabras en el título, porque las columnas repiten su nombre.
- **El mismo medio ya no cuenta doble con su versión AMP** (27/10/2026): `amp.milenio.com` es `milenio.com`.
- **La «fecha del hecho» ya no dice que algo «ocurrió» ese día** (27/10/2026): la IA suele dar la fecha de los antecedentes. La vinculación de Jáuregui del 25/10 salía como del 1 de abril. Ahora dice «Se refiere a hechos del…».
- **El mapa carga más rápido al ir de una nota a otra** (27/10/2026): MapLibre 6 decodificaba las teselas de calles con un solo hilo, de una en una, y el mapa se veía gris y se iba llenando poco a poco. Ahora usa la mitad de los procesadores, hasta 4 hilos (4 en la computadora de Benji), y los nombres aparecen en 120 ms en lugar de 300.
- **«Ver nota original» se abre en una pestaña nueva también en el navegador integrado** (27/10/2026): todos los enlaces a notas abren una ventana nueva al hacer clic, sin tocar la pestaña del monitor. Ctrl+clic y clic con la rueda siguen igual.
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
