# ADR-0045: Envíos por usuario: cada quien sus correos y sus horas

- **Estado:** aceptada; las horas por correo (punto 3) las reemplaza [ADR-0046](0046-envios-programados.md)
- **Fecha:** 2026-11-11
- **Fase:** F12
- **Relacionadas:** ADR-0039 (envíos), ADR-0040 (horario único), ADR-0042 (seguridad por filas), ADR-0043 (acceso con contraseña)

## Contexto

Hasta ahora «Envíos» era solo del superusuario: él daba de alta a todos los destinatarios y cada corrida del horario único (07:00, 15:00 y 23:00) se mandaba a todos.

Con usuarios propios (ADR-0043), Benji pidió (10 y 11/11/2026):

- «Que ellos agreguen su correo y ya les van a estar empezando a llegar las noticias.»
- «Van a poder elegir cosas como sus horarios.»
- «No van a modificar cosas como el correo emisor, porque ese va a estar definido por nosotros.»
- «En la parte de sus envíos tiene que estar todo limpio.»
- Por ahora, lo de la Fiscalía a las horas de siempre. Las automatizaciones con temas propios llegan después.

## Decisión

1. **Cada destinatario y cada envío tienen dueño** (migración 0042).
   - `delivery_recipients.owner` y `deliveries.owner` guardan el `username`.
   - Lo que ya existía quedó a nombre de `benji`, así que lo de Benji sigue igual.
   - El envío toma el dueño de su destinatario.
2. **La separación la hace la base.** La seguridad por filas aplica en `delivery_recipients` y `deliveries` con la misma política de ADR-0042: `app_privileged() OR owner = app_username()`.
   - Cada persona ve, edita, borra, prueba y reintenta solo lo suyo.
   - El superusuario y el worker ven todo.
   - Aunque una ruta olvidara filtrar, la base no deja ver lo ajeno.
3. **Cada quien elige sus horas.** `delivery_recipients.hours` guarda los minutos del día, como `monitor_schedule.times`.
   - Las horas se eligen solo entre las del horario vigente.
   - Vacío = a todas las horas: es lo que hay por omisión y lo que tenían los destinatarios que ya existían.
   - Al terminar cada corrida, `PlanDeliveries` manda solo a quien quiere esa hora (en hora de la Ciudad de México).
4. **Tope de dos correos por usuario normal** (`MAX_RECIPIENTS_PER_USER`). El superusuario no tiene tope: maneja listas.
5. **El correo emisor es fijo.**
   - Las cuentas (`/deliveries/accounts`), las reglas (`/deliveries/rules`) y cambiar el horario (`PUT /schedule`) piden superusuario.
   - «Mandar prueba» de un usuario ignora `account_id` y siempre sale de la cuenta de la regla de correo.
   - La pantalla le muestra a la persona desde qué correo le llega (`overview.sender_address`).
6. **El reporte de la corrida se lee como el sistema.**
   - `PostgresRunReports` usa `as_system()`: la corrida automática queda a nombre de quien la lanzó, pero su reporte es para todos los que reciben envíos.
   - Solo lee búsquedas con `trigger = 'automatic'`, nunca las de una persona.
7. **Pantalla.**
   - El usuario normal ve «Mis envíos»: sus correos, las horas como botones, «Mandar prueba» sin elegir cuenta y su historial.
   - El superusuario ve la pantalla completa, con el dueño de cada correo y de cada envío.

## Alternativas consideradas

- **Que cada usuario tenga su propio horario o sus propias corridas.** Cada hora distinta es otra corrida con IA. Se deja para la Entrega B (automatizaciones propias, máximo 3 al día), agrupando las corridas iguales.
- **Filtrar por dueño en el código, sin RLS.** Es más simple, pero un olvido en una ruta mostraría los correos de otros. RLS ya está probada en búsquedas y reportes (ADR-0042).
- **Dejar que el usuario elija la cuenta emisora.** Benji lo descartó: el correo que envía lo definen ellos.

## Consecuencias

- Un usuario normal entra a «Envíos», agrega su correo y le empieza a llegar el reporte de la FGR desde la siguiente corrida, sin que el administrador haga nada.
- Si dos personas ponen el mismo correo, la corrida le llega una sola vez: la llave de idempotencia es fuente + corrida + canal + destino. El envío queda a nombre de la primera.
- Si el superusuario quita del horario una hora que alguien eligió, esa hora simplemente deja de contar.
  - Si a la persona le quedan otras horas válidas, recibe solo esas.
  - Si no le queda ninguna, recibe **todas**, igual que si no hubiera elegido. Así la pantalla («A todas las horas del horario») y lo que llega dicen lo mismo, y nadie se queda sin reporte por un cambio de horario.
  - La corrida le pasa a `PlanDeliveries` el horario vigente para decidirlo. Las horas viejas se quitan la próxima vez que la persona guarde.
- `delivery_attempts` no tiene RLS: se lee solo después de abrir su envío, que sí la tiene.
