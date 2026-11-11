# ADR-0046: Envíos programados: cada quien sus temas, región, horas y días

- **Estado:** aceptada
- **Fecha:** 2026-11-11
- **Fase:** F12
- **Relacionadas:** ADR-0040 (horario único, reemplazado), ADR-0045 (envíos por usuario; sus horas por correo se reemplazan), ADR-0031 (corridas automáticas), ADR-0042 (seguridad por filas)

## Contexto

ADR-0045 dejó que cada usuario agregara sus correos y escogiera entre las tres horas fijas de la FGR (07:00, 15:00 y 23:00). Benji lo probó y pidió otra cosa (11/11/2026):

- «Necesito que él pueda personalizar los envíos.»
- «Si ahora quiere que se envíe el reporte de tal cosa a las 4 de la tarde y a las 8 de la noche, lo puede personalizar totalmente desde ahí. Eso aplica tanto para él como para mí.»
- «No pongas desde qué correo se envía.»

Además decidió:

- un tope de **3 corridas al día por usuario normal**; el superusuario, hasta 8;
- que cada usuario nuevo empiece con una copia de la FGR a las 07:00, 15:00 y 23:00.

## Decisión

1. **El envío programado** (tabla `delivery_schedules`, migración 0043) es lo que arma cada persona:
   - nombre;
   - temas (conceptos), de 1 a 5;
   - región: país, estado o municipio;
   - horas libres al minuto, con las reglas del horario (máximo 8 y al menos una hora de separación);
   - días de la semana;
   - a cuáles de sus correos va (`delivery_schedule_recipients`);
   - prendido o apagado.
2. **Dueño y seguridad por filas**, como en ADR-0045: cada quien ve y cambia solo los suyos; el superusuario y el worker ven todos.
   - Solo se puede mandar a correos **del dueño del envío**.
   - Los temas y la región tienen que existir.
3. **Tope diario**: 3 corridas al día para un usuario y 8 para el superusuario. Se suman todos sus envíos prendidos y se cuenta el día de la semana con más corridas. Un superusuario que edita el envío de otra persona no queda limitado por ese tope.
4. **El reloj**, que revisa cada minuto, ya no lee el horario único: lee todos los envíos prendidos que tienen correos (`PendingRuns`).
   - Cada envío que llega a una de sus horas pide una corrida que cubre **desde su hora anterior**: el de 16:00 y 20:00 trae a las 20:00 lo de 16:00 a 20:00.
   - **Corridas iguales se agrupan**: mismos temas, misma región, misma hora y mismo periodo hacen una sola corrida con IA, que les llega a todos esos envíos (`due_runs`). Así, las copias de la FGR de todos los usuarios cuestan lo mismo que una.
   - Cada corrida se aparta en `delivery_schedule_claims` con su llave (tema + periodo), para no lanzarla dos veces.
   - Un envío sin correos no lanza nada.
5. **La corrida** (`run_scheduled_job`) busca esos temas en esa región con las fuentes gratis de siempre.
   - Guarda su tema en `searches.topic_key`: el reporte separa lo nuevo comparando con la corrida anterior **del mismo tema**.
   - Su PDF se llama `corrida_AAAA-MM-DD_HHMM_<búsqueda>.pdf`, porque a la misma hora puede haber varias corridas.
   - Manda el reporte solo a los correos de los envíos que la pidieron.
   - El asunto dice qué buscó: «Reporte FGR · México · corrida …».
6. **Datos que ya existían** (migración 0043):
   - el horario único de hoy se volvió el envío «Monitor FGR» de Benji, con sus correos;
   - cada usuario existente recibió su copia, con sus correos si tenía.
7. **Usuario nuevo**: al crearlo, `AccessAdmin` llama a `StarterSchedule`, que le da su «Monitor FGR» 07:00/15:00/23:00 (sale de `AUTOMATIC_CONCEPT`, `AUTOMATIC_REGION_CODE` y `AUTOMATIC_RUN_HOURS`). No corre hasta que agregue un correo.
8. **Pantalla**:
   - «Mis envíos» para todos: lista de envíos programados con su próxima corrida, «+ Nuevo envío», «Mis correos» e historial.
   - El superusuario ve además las cuentas de envío y los envíos de todos, con su dueño.
   - **No se muestra desde qué correo se envía.** `overview.sender_address` solo llega al superusuario.
   - La cuenta regresiva de «Mando» usa la próxima corrida de los envíos de la persona.
9. **Se quitan las horas por correo** de ADR-0045: las horas viven en cada envío.
10. **`make corrida-fgr`** sigue corriendo a mano la corrida FGR de siempre, pero **ya no manda correos**: eso lo hacen los envíos programados.

## Alternativas consideradas

- **Seguir con un horario único y que cada quien elija horas de ahí** (ADR-0045). Benji lo descartó: no deja escoger otro tema ni otra hora.
- **Una corrida por envío, sin agrupar.** Es más simple, pero 30 copias de la FGR serían 30 corridas con IA a la misma hora. Agrupar las iguales cuesta lo mismo que una.
- **Que el usuario elija también las fuentes.** Se quedan las gratis de siempre (Google News RSS e índice local). Así una corrida automática nunca gasta créditos de SearchApi.

## Consecuencias

- **Costo.** Cada corrida distinta cuesta unos US$0.04. Con 30 usuarios y 3 corridas diarias cada uno, todas distintas, el peor caso son unos US$108 al mes. Lo que se repite se agrupa y no cuesta más.
- **Fila de espera.** Muchas corridas distintas a la misma hora se forman en el worker. Las últimas pueden llegar unos minutos tarde. Una que no empieza en 2 horas se descarta (`AUTOMATIC_RUN_EXPIRES_SECONDS`).
- **Lo que quedó sin uso** y se borra en otra migración, con permiso de Benji:
  - la tabla `monitor_schedule` y sus apartados `monitor_schedule_claims`;
  - la ruta `/schedule` y la pantalla `SchedulePanel.tsx`;
  - la columna `delivery_recipients.hours`.
- **Las corridas automáticas** siguen firmadas por `AUTOMATIC_USER`: el usuario recibe el PDF por correo, pero todavía no las ve en su historial del monitor.
