# ADR-0022: Las corridas automáticas FGR se programan en el reloj de Celery que ya existe

- **Estado:** Aceptado
- **Fecha:** 24 de octubre de 2026
- **Fase:** F12 (monitor automatizado FGR; se implementa en F12.8)
- **Decide:** Benji («los horarios de los reportes fijos y automatizados… a las 7 am, 3 pm y 11 pm»)

## Contexto

El plan de la Fase 12 (`docs/PLAN_MONITOR_FGR.md`, §4.3) pide una búsqueda automática de la FGR a las **07:00, 15:00 y 23:00, hora de la Ciudad de México**. Cada una guarda su corrida, sus notas y su reporte en PostgreSQL. El plan dejó abierto si usar Celery beat o APScheduler.

Lo que ya existe:
- `make up` levanta un worker de Celery y su reloj (`celery beat`, ADR-0005).
- El reloj ya dispara dos tareas en `backend/app/worker/celery_app.py` (`build_beat_schedule`): la ingesta al índice local cada `INGEST_INTERVAL_MINUTES`, y la purga diaria con `crontab` a las 09:30 UTC.
- La app trabaja en UTC (`timezone="UTC"`, CLAUDE.md §6.3).
- México no cambia de horario desde el 30 de octubre de 2022 (Ley de los Husos Horarios): la Ciudad de México está fija en UTC−6.

## Decisión

1. **Las corridas FGR son una entrada más del `beat_schedule`**, con `crontab`, junto a la ingesta y la purga. Las ejecuta el mismo worker.
2. **La app sigue en UTC.** Las horas se escriben en la configuración en hora de la Ciudad de México y el código las convierte a UTC con `zoneinfo("America/Mexico_City")` al armar el horario. Hoy, 07/15/23 h CDMX equivalen a 13/21/05 h UTC. La conversión no se hace a mano en el código.
3. **Configurable por `.env`.** Se proponen `MONITOR_RUN_HOURS=7,15,23` y `MONITOR_TIMEZONE=America/Mexico_City`; los nombres finales se fijan en F12.8 y se documentan en `.env.example`.
4. **No se enciman.** Si una corrida no alcanza a empezar antes de la siguiente, se descarta (`expires`), igual que la ingesta. La ventana de cada corrida es «desde la última corrida terminada», así que una corrida perdida no deja hueco de notas: la siguiente las cubre.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| APScheduler | Sería otro programador, otro proceso que vigilar y una dependencia nueva, para hacer lo que el reloj de Celery ya hace. |
| Poner Celery en `America/Mexico_City` | Cambiaría la zona de todas las tareas y de las fechas de Celery; la regla del proyecto es UTC en todo. |
| Escribir 13/21/05 UTC fijos | Funciona hoy, pero esconde la intención («7 de la mañana en CDMX») y se rompe en silencio si la regla de horario cambia. |
| Cron del sistema operativo | Queda fuera del proyecto, no viaja con `make up` ni con la migración a Proxmox y no deja logs en JSON. |

## Consecuencias

- No se instala nada nuevo. Lo único que cambia en `celery_app.py` es una entrada más en `build_beat_schedule`, con su prueba.
- Las corridas dependen de que corran el reloj **y** el worker. `make status` ya muestra los dos. Hasta la migración a Proxmox (F12.9), corren en la PC de Benji, que está siempre prendida.
- Si México volviera a cambiar de horario, basta con reiniciar el reloj (`make down && make up`) para que las horas se vuelvan a calcular.
- **`# VERIFICAR` en F12.8:** si el reloj estuvo apagado a la hora de una corrida, revisar si `celery beat` la lanza al arrancar o la salta. La ventana «desde la última corrida» cubre las notas en los dos casos, pero el reporte de esa hora se generaría tarde o no se generaría.
