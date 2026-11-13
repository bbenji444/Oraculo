# ADR-0039: Envíos auditables con Composio

- **Estado:** Aceptado (07/11/2026). Es un prototipo funcional para presentar.
- **Fecha:** 7 de noviembre de 2026
- **Fase:** F12.11
- **Decide:** Benji. Pidió una sección «Envíos» en el monitor:
  - elegir la cuenta de correo (Gmail, Outlook o Hotmail);
  - tener el botón de WhatsApp aunque todavía no funcione;
  - que el correo funcione de verdad;
  - y que se pueda proponer después como el módulo de envíos de todo Oráculo: «a quién se le va a estar enviando qué y a qué hora».

## Contexto

Cada corrida automática del monitor FGR (07:00, 15:00 y 23:00) deja su PDF en `REPORTS_DIR`, pero nadie lo recibe. Oráculo hoy automatiza con n8n, y el plan de automatización (`docs/PLAN_AUTOMATIZACION.md`) pide envíos con historial auditable, en código propio.

El 06/11/2026 se probó Composio a mano: un script mandó el PDF desde la cuenta Ovitech hacia Benjamin, sin pasar por Claude. Funcionó.

## Decisión

1. **La sección vive en el monitor, pero no depende de él.** Cada envío lleva una `source` (de dónde viene lo que se manda; hoy `monitor.corrida_fgr`) y una `source_ref` (cuál: el id de la corrida). Las tablas, el dominio y la API no usan tablas del monitor. Pasarlo a un módulo general es sacar esta carpeta y agregar fuentes.
2. **Cinco tablas** (migración 0035):
   - **cuentas de envío:** Outlook o Gmail vía Composio, y el lugar reservado para WhatsApp;
   - **destinatarios;**
   - **reglas:** fuente, destinatario, canal, cuenta y horas; sin horas = todas las corridas;
   - **guías de envío:** estado, intentos, error y número del proveedor;
   - **intentos.**

   La llave `idempotency_key` impide mandar dos veces la misma corrida al mismo destino.
3. **Composio manda el correo.** Es el «llavero» de las cuentas:
   - el monitor usa la librería `composio` (0.31) con una llave de **proyecto** (`ak_`) en `COMPOSIO_API_KEY`;
   - las cuentas pertenecen al usuario de Composio `oraculo-monitor`;
   - conectar una cuenta desde la pantalla crea, si falta, la configuración de Outlook o Gmail administrada por Composio, y devuelve un link para autorizarla;
   - la librería **solo puede subir archivos de `REPORTS_DIR`**, para que nunca adjunte por error el `.env` u otro archivo.
4. **Reintentos y registro:**
   - cada intento queda en `delivery_attempts`;
   - un error pasajero (red, límite) se reintenta a los 1, 5 y 30 minutos;
   - un error permanente (permiso, destino inválido) o el cuarto fallo dejan la guía en «falló»;
   - el botón **Reintentar** crea un intento nuevo sin borrar los anteriores;
   - una guía que se queda «enviando» más de 15 minutos se cortó a medias (el servidor se reinició mientras salía). Cuenta como un intento fallido y vuelve a la fila en la siguiente pasada. Si el correo sí alcanzó a salir, llega dos veces; es preferible a que no llegue (añadido el 12/11/2026, cuando un reinicio de la VM dejó atorado el correo de Geovanni de las 07:00);
   - el reloj de Celery revisa lo pendiente cada minuto.
5. **Interruptor general apagado por defecto** (`DELIVERIES_ENABLED=false`). Las corridas no mandan nada hasta encenderlo. «Mandar prueba» sí funciona: manda ya la última corrida a una persona.
6. **WhatsApp:** el botón aparece como «Próximamente». El canal existe en el modelo y su emisor responde «todavía no». Llega con la API oficial de Meta y una plantilla aprobada (`docs/PLAN_AUTOMATIZACION.md` §4.4).

## Alternativas consideradas

- **Dejarlo en n8n.** Es lo que se quiere sustituir: los flujos son difíciles de versionar y probar, y la auditoría avanzada es de pago.
- **Que Claude mande los correos.** Necesitaría a Claude Code abierto a cada hora, cuesta tokens y es más difícil de auditar. Claude construye; el monitor manda.
- **SMTP directo.** Funciona, pero cada proveedor pide su configuración y contraseñas de aplicación. Composio resuelve la autorización (OAuth) y deja la puerta abierta a más apps (Slack, Drive, WhatsApp).
- **Un módulo aparte desde ya.** Hoy solo hay una fuente. Se construye dentro del monitor pero desacoplado, y se separa cuando llegue la segunda.

## Consecuencias

- **Dependencia nueva:** `composio`. Su librería cambia seguido: el 07/11/2026 ya había un método retirado (`initiate` para cuentas administradas). Todo el uso está en `app/adapters/delivery/composio_channels.py`.
- **Los reportes pasan por Composio y por Microsoft o Google.** Se aceptó para el prototipo. Para clientes reales conviene una cuenta de la empresa en lugar de un Hotmail personal (que tiene límites diarios).
- **Probado el 07/11/2026:**
  - desde la pantalla, «Mandar prueba» de Ovitech a Benjamin con el PDF de la corrida del 06/11 a las 15:00 quedó «Enviado» en 1 intento;
  - las pruebas automáticas usan un cliente falso y nunca mandan nada.
- **Para encender los envíos de las corridas:** revisar las reglas y poner `DELIVERIES_ENABLED=true`.

## Adenda (07/11/2026): reglas abiertas y regla general

> **Reemplazada por ADR-0040 (06/11/2026):** ya no hay reglas por persona ni horas por regla; hay un horario único de corridas y cada reporte va a todos.

Benji vio la primera versión y pidió otra forma: «eso se ve horrible, lo de que tenga una regla individual para cada persona». Quiere una **regla general** («a todos, a las 7, 3 y 11») y poder poner o quitar horas.

- **Migración 0036.** Una regla ya no es «una persona + horas de corrida». Ahora tiene:
  - `name`;
  - `audience`: `all` (todos los destinatarios activos, menos `exclude_ids`) o `selected` (solo `recipient_ids`);
  - `times`: minutos del día (09:30 = 570), cualquier hora, no solo las de las corridas;
  - `days`: días ISO (1 = lunes); vacío = todos.

  Las reglas viejas se convierten solas: su persona pasa a `recipient_ids` y sus horas a minutos; sin horas = 07:00, 15:00 y 23:00.
- **Horas sin corrida.** A las horas de corrida se sigue mandando el reporte nuevo al terminarla (`PlanDeliveries.for_run`). A las demás horas, el reloj de Celery (cada minuto) manda el reporte más reciente (`PlanDeliveries.scheduled`). La llave de esas guías lleva la hora («2026-11-07 09:30») para que no se repita en el mismo minuto, y la guía guarda `scheduled_for`.
- **Pantalla.**
  - «Programación de envíos»: la regla general, las reglas personalizadas como tarjetas que se despliegan y los próximos envíos.
  - Cada destinatario se edita desplegando su perfil, y «+ Agregar» abre una ventana.
  - Se pueden borrar reglas y destinatarios. Un destinatario borrado sale de las reglas, y su historial se conserva.
- **Alternativa descartada:** una tabla aparte de «audiencias». Por ahora basta con dos listas en la regla. Si llegan grupos («clientes de Jalisco»), se agrega una tabla de grupos sin cambiar las guías.
