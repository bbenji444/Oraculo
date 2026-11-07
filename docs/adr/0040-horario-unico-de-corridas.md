# ADR-0040: Horario único de las corridas, editable por el administrador

- **Estado:** aceptada
- **Fecha:** 2026-11-06
- **Fase:** F12
- **Relacionadas:** ADR-0031 (corridas automáticas), ADR-0034 (auditoría de corridas), ADR-0039 (envíos auditables)

## Contexto

Benji programó en «Envíos» una regla a las 22:19 y no llegó nada. Revisamos y había dos causas:

- los envíos estaban apagados (`DELIVERIES_ENABLED=false`);
- aunque estuvieran prendidos, una hora sin corrida solo **reenviaba el último reporte**.

Además, las horas de las corridas (07:00, 15:00 y 23:00) estaban fijas en el `.env` y la pantalla no podía moverlas.

Benji fijó la regla, «súper importante» (06/11/2026):

- **Envíos es solo para el administrador** (el equipo interno). Los usuarios no automatizan nada por su cuenta: cada horario distinto sería otra corrida y un consumo alto de tokens.
- **Hay un solo horario para todos.** Agregar, cambiar o quitar una hora aplica a todos.
- **A cada hora se hace un reporte totalmente nuevo**, desde la hora anterior hasta esa. Por ejemplo, si agrega las 19:00 entre las 15:00 y las 23:00:
  - la de las 19:00 cubre de 15:00 a 19:00;
  - la de las 23:00 pasa a cubrir de 19:00 a 23:00.
- La hora se queda programada hasta que él la quite: «modular y editable, como si fuera un n8n, pero desde esta plataforma».

## Decisión

1. **El horario vive en la base** (`monitor_schedule`, una sola fila, migración 0037):
   - horas en minutos del día y días de la semana (vacío = todos);
   - mientras nadie lo edite, vale `AUTOMATIC_RUN_HOURS` del `.env`;
   - se edita en «Envíos → Horario de las corridas» o con `PUT /schedule`;
   - cada cambio queda en la bitácora (`schedule.updated`, con el antes y el después).
2. **El reloj revisa cada minuto** (`monitor.schedule_tick`) en lugar de un `crontab` fijo:
   - si llegó una hora del horario (con 10 minutos de gracia), la aparta en `monitor_schedule_claims` y encola la corrida;
   - la llave primaria impide lanzar dos veces la misma hora aunque el worker tarde en tomarla;
   - un cambio en la pantalla aplica en el minuto siguiente, sin reiniciar nada.
3. **Cada corrida cubre desde la hora programada anterior** del horario vigente (`RunSchedule.window`). Así sigue la regla del 28/10/2026 («solo el periodo anterior al periodo actual»), ahora con horas libres al minuto y días de la semana. Con días limitados, la primera corrida de la semana cubre desde la última de la semana anterior.
4. **Topes contra el consumo:**
   - máximo **8 horas al día**;
   - al menos **60 minutos** entre una hora y la siguiente, contando la última del día con la primera del siguiente;
   - la pantalla muestra el costo promedio de una corrida (últimas dos semanas; ≈ US$0.038 al 06/11/2026) y cuánto suma a la semana.
5. **Los envíos van a todos.**
   - Se quitan las reglas personalizadas y las horas por regla de ADR-0039 (adenda del 07/11).
   - `delivery_rules` queda como «cómo se manda cada fuente»: canal, cuenta y si está prendida, con una por fuente y canal.
   - Al terminar cada corrida, su reporte se manda a todos los destinatarios con «Recibe envíos» prendido. Para que alguien no lo reciba, se apaga ese interruptor.
   - Ya no existe «reenviar el último reporte».
6. **Restricción a administradores:** por ahora no hay inicio de sesión. Benji decidió esperar a la integración con Oráculo para restringir `/schedule` y `/deliveries` al rol de administrador.

## Alternativas consideradas

- **Reenviar el último reporte a horas extra** (lo que hacía la adenda de ADR-0039). Es barato, pero manda información vieja. Benji lo descartó.
- **Horarios por usuario o por cliente.** Multiplica las corridas y los tokens. Benji lo prohibió.
- **Reprogramar el `crontab` de Celery al guardar.** Obliga a reiniciar el reloj y no permite minutos ni días sin reescribir la configuración. Revisar la base cada minuto cuesta una consulta por minuto y aplica al instante.
- **Clave de administrador en el `.env`.** Era una protección inmediata, pero Benji prefirió esperar al inicio de sesión de Oráculo.

## Consecuencias

- **Cada hora agregada es una corrida más de IA.** Los topes y el aviso de costo lo contienen.
- **Las reglas personalizadas se borraron** al migrar (aprobado por Benji). Los envíos pasados se conservan con `rule_id` vacío.
- **`make corrida-fgr` sigue funcionando.** Usa la hora del horario vigente a la que pertenece el momento y no aparta la hora, así que sirve para repetir una corrida a mano.
- **Si el reloj estuvo apagado más de 10 minutos después de una hora, esa corrida se pierde.** Se recupera a mano con `make corrida-fgr`, igual que antes con la caducidad de 2 horas.
- **El Centro de mando** («Próxima corrida») lee el mismo horario.
- **Verificado el 06/11/2026:**
  - en la pantalla, agregar las 19:00 mostró «desde 15:00» y las 23:00 pasaron a «desde 19:00»;
  - se guardó con su bitácora;
  - `PUT /schedule` con 15:00 y 15:30 respondió `422 invalid_schedule`.
