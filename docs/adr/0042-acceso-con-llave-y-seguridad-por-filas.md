# ADR-0042: Acceso con llave, roles y seguridad por filas

- **Estado:** aceptada (piloto solo en el monitor; etapa 1 de 3)
- **Fecha:** 2026-11-10
- **Fase:** F12
- **Relacionadas:** ADR-0039 (envíos), ADR-0040 (horario único), `docs/PLAN_AUTENTICACION.md` (plan para todo Oráculo)

## Contexto

Hasta hoy el monitor no pedía nada: todo se hacía a nombre de un usuario fijo de desarrollo («desarrollo»). Al pasar al servidor (VM 108), cualquiera en la red de la oficina o en ZeroTier podía abrirlo, ver todas las búsquedas y cambiar el horario de los correos.

Benji pidió (10/11/2026):

- entrar con un **«token» como el de la API de ChatGPT o de Claude**, con seguridad «altísima» (lo pidió su jefe);
- probarlo **primero solo en el monitor** y, si funciona, llevarlo a todo Oráculo;
- **usuarios normales** con Explorar, Casos, Conceptos, Historial y Envíos, y **«Estado del sistema» solo para superusuarios**;
- que **cada persona tenga su propio historial** y que la separación la haga la base (**RLS**);
- que su usuario quede **tal cual**: corridas de 07:00, 15:00 y 23:00, envíos y conceptos;
- que los usuarios sean **totalmente administrables** desde el perfil de superusuario.

Lo que ya existía en Oráculo (`apis_control.api_keys` en el servidor de APIs) guarda la llave en texto plano y la recibe en la URL. No sirve como modelo (detalle en `docs/PLAN_AUTENTICACION.md`).

## Decisión

### 1. Llaves con formato de API conocida

- **Formato:** `orc_live_<8 públicos>_<40 secretos>` (58 caracteres, ~238 bits al azar con `secrets`).
  - El prefijo `orc_` deja que los detectores de secretos reconozcan una llave subida por error.
  - La parte pública identifica la llave en pantallas y bitácora sin revelarla (`orc_live_a1b2c3d4…`).
- **En la base solo la huella:** HMAC-SHA256 de la llave con una «pimienta» (`AUTH_KEY_PEPPER`) que vive en el `.env`, fuera de la base. Si alguien roba la tabla, las huellas no sirven para entrar.
  - No hace falta bcrypt: las llaves son largas y al azar, no contraseñas que se adivinen.
- **Se compara en tiempo constante**, y con una llave inexistente se calcula igual una huella, para no dar pistas por lo que tarda.
- **El mismo mensaje** para llave inexistente, revocada, vencida o de alguien desactivado.
- **Vigencia elegible:** 30, 90 (recomendado), 180 o 365 días, o sin vencimiento.
- **Tope de 5 llaves vigentes por persona.**
- **Revocación inmediata.**

### 2. Dos formas de usarla

- **Pantalla:** se pega la llave una vez en «Entrar» (`POST /auth/login`, en el cuerpo y nunca en la URL). La API abre una **sesión** y responde con una cookie:
  - `HttpOnly`: el JavaScript no la puede leer, así que un script malicioso tampoco;
  - `SameSite=Strict` y `Path=/api`;
  - dura a lo más **8 horas** y se cierra tras **60 minutos sin uso**;
  - en Redis se guarda la huella SHA-256 del valor de la cookie, no el valor.
- **Integraciones** (otros módulos de Oráculo): `Authorization: Bearer orc_live_…` en cada petición, como en OpenAI.
- **CSRF:** con cookie, las peticiones que cambian algo deben traer `Origin` (o `Referer`) del mismo servidor; si no, 403. Para eso nginx ahora pasa `Host` con su puerto (`$http_host`).
- **Freno de intentos:** 10 fallos por IP en 15 minutos bloquean esa IP hasta que pase la ventana (429).
- **Revisión periódica:** cada 5 minutos la sesión vuelve a revisar en la base que la llave y la persona sigan activas y toma su rol actual. Revocar una llave o desactivar a alguien, además, **cierra sus sesiones al instante**.

### 3. Roles

| Rol | Pestañas | Además |
|---|---|---|
| `superuser` | Todas, también «Estado del sistema» y «Accesos» | Ve el historial de todos («Ver de todos»); cambia conceptos, subdivisiones, horario y envíos |
| `user` | Explorar, Casos, Conceptos, Historial | Lanza sus búsquedas y ve solo las suyas |

El servidor decide las pestañas (`GET /auth/me` → `sections`) y cada ruta revisa el rol: esconder una pestaña no basta.

Reglas que protegen al sistema:

- nadie se quita a sí mismo el rol ni se desactiva;
- siempre queda al menos un superusuario activo;
- nadie revoca su única llave vigente.

### 4. Seguridad por filas (RLS) en PostgreSQL

La API le dice a PostgreSQL quién pregunta **en cada transacción**, con dos variables locales a la transacción: `app.role` y `app.username`. Las pone `create_api_engine` (`app/adapters/persistence/access_scope.py`).

Las conexiones de la API nacen como `anonymous`: si algo se consulta sin persona, no ve nada protegido.

Políticas (migración 0039, con `FORCE` para que valgan también para el dueño de las tablas):

- **`searches`:** las propias (`user_id`) o todas si es `superuser` o `system`. Tampoco se puede **guardar** una búsqueda a nombre de otro (`WITH CHECK`).
- **`search_results`, `search_concepts`, `processing_errors`, `reports`:** las de una búsqueda que la persona puede ver.
- **`users`, `access_keys`:** solo superusuarios y el sistema. Revisar una llave al entrar corre como `system`, porque todavía no se sabe quién es.

El worker, el reloj, los comandos (`make …`) y Alembic no ponen variables y las políticas los tratan como `system`: corren en el servidor, no por HTTP. El rol de la base `monitor` no es superusuario de PostgreSQL (si lo fuera, se saltaría las políticas). Se revisó en la PC y en el servidor general.

Así, aunque una ruta nueva olvidara filtrar, la base no entrega búsquedas ajenas. Las pruebas de integración lo comprueban contra PostgreSQL real.

### 5. Los datos de Benji quedan igual

La migración 0038 crea al superusuario `benji` y pasa a su nombre lo que era de «desarrollo»:

- búsquedas;
- casos y sus miembros;
- conceptos;
- reportes.

La bitácora no se reescribe. Las corridas automáticas siguen firmadas por `monitor-automatico` y las ve el superusuario.

### 6. Primera llave por consola

`make crear-llave ARGS="--usuario benji --dias 365"` la muestra **una vez** en la terminal (nunca en logs). Con `--archivo` la escribe en un archivo con permisos `600`.

Sirve para la primera llave y para recuperar el acceso si se pierden todas. Después todo se hace en «Accesos».

### 7. Modos

- `AUTH_MODE=keys` es el valor por omisión, y sin pimienta la API no arranca.
- La PC de desarrollo y las pruebas usan `AUTH_MODE=dev`: se entra sin llave como `DEV_USER` (superusuario).

## Alternativas consideradas

- **Copiar `apis_control.api_keys` de Oráculo.** Guarda la llave en texto plano y la recibe en la URL, donde queda en logs e historiales. Se descartó; el plan general propone migrarlo a este esquema.
- **Contraseñas por persona.** Benji pidió llaves tipo API, y las contraseñas exigen hash lento, recuperación y políticas de complejidad.
- **JWT sin estado.** No se pueden revocar al instante sin una lista negra, que vuelve a ser estado. Una sesión en Redis es más simple y revocable.
- **Filtrar solo en la aplicación (sin RLS).** Un descuido en una ruta nueva filtraría datos. Benji pidió RLS explícitamente.
- **Guardar la llave en `localStorage`.** Cualquier script de la página la podría leer. La cookie `HttpOnly` no.

## Consecuencias

- **Entrar.** Cada persona necesita una llave que le da un superusuario. Si la pierde, se le crea otra y se revoca la vieja.
- **Pimienta.** Si `AUTH_KEY_PEPPER` cambia o se pierde, todas las llaves dejan de servir. Se recupera con `make crear-llave` en el servidor.
- **HTTPS.** Se sirve por `http://` en la red interna y ZeroTier, por eso `AUTH_COOKIE_SECURE=false`. Con HTTPS hay que ponerlo en `true`.
- **Etapa 1 de 3.** Mientras tanto, conceptos, subdivisiones, horario y envíos los cambia solo el superusuario; los usuarios normales los ven, pero no los editan.
  - Etapa 2: conceptos y subdivisiones propios de cada persona.
  - Etapa 3: envíos y corridas automáticas propios de cada persona (de 1 a 2 correos, hasta 3 corridas al día).
- **Rendimiento.** Para un superusuario la política se resuelve sin consultar nada más (medido: 3 ms para abrir una búsqueda). Para un usuario normal, cada fila hija se revisa contra `searches`, que es una tabla chica.
- **Nuevas tablas por persona.** Si se agregan, necesitan su política en una migración.
