# ADR-0031: Corridas automáticas del monitor FGR: una búsqueda nacional a las 07:00, 15:00 y 23:00 con fuentes gratis

- **Estado:** Aceptado
- **Fecha:** 26 de octubre de 2026
- **Fase:** F12.8
- **Decide:** Benji (plan F12 §1 y §9.1: «los reportes automatizados a las 7 am, 3 pm y 11 pm», «que TODO se vaya guardando en Postgres», una búsqueda nacional por corrida, solo fuentes gratis; el 26/10/2026: «la automatización de las búsquedas de la FGR con la base de GDELT y el Google News RSS»)

## Contexto

El monitor tiene que buscar solo a la FGR en todo México tres veces al día y dejar cada corrida guardada con sus notas y su reporte. Ya existen todas las piezas:

- el reloj de Celery (ADR-0022), que ya corre la ingesta y la limpieza;
- el pipeline de búsqueda, que extrae, resume, ubica, clasifica (ADR-0029, ADR-0030) y agrupa historias;
- el reporte (ADR-0018).

Faltaba unirlas sin que una persona lo pida.

## Decisión

1. **Una tarea del reloj** (`monitor.automatic_run`) a las 07:00, 15:00 y 23:00 de la CDMX.
   - El reloj trabaja en UTC: se programa a las 05:00, 13:00 y 21:00, porque la CDMX está en UTC-6 todo el año desde octubre de 2022.
   - Si la corrida no empieza en 2 horas, se descarta (`expires`): la siguiente cubre los mismos días.
2. **La corrida es una búsqueda como cualquier otra**, armada con un perfil fijo de configuración (`AUTOMATIC_*`):
   - concepto «Fiscalia General de la Republica» (con su regla FGR federal);
   - región `MEX` (todo México; la geolocalización reparte por estado);
   - hoy y ayer;
   - solo **Google News RSS** y el **índice local**, que se llena cada 15 minutos con GDELT y los RSS de los medios. Son 0 créditos y sin captchas.
3. **Pasa por las mismas reglas que una manual** (`StartSearch`): tope de consultas, llave de la IA y tope de créditos. Corre en el mismo worker, con el mismo pipeline. La única diferencia es el tope de notas que lee la IA: `AUTOMATIC_LLM_MAX_ARTICLES` (250) en lugar de `LLM_MAX_ARTICLES_PER_SEARCH` (150). La corrida de las 15:00 del 27/10/2026 llegó al tope general y 10 notas esperaron a la siguiente. Benji lo subió a 250, unos 0.025 USD más por corrida en el peor caso.
4. **Se guarda todo en PostgreSQL** (migración 0028):
   - la búsqueda, marcada `searches.trigger = 'automatic'`, con su `scheduled_for`;
   - sus notas (`search_results`), la bitácora y el reporte (`reports`);
   - la ruta del PDF, que se guarda en `REPORTS_DIR` como `fgr_AAAA-MM-DD_HHMM.pdf` (`reports.pdf_path`).
5. **Las corridas automáticas las ve todo analista** en su historial. Una manual la sigue viendo solo quien la pidió.
6. **Repetir días no cuesta:** una nota que ya leyó la IA en otra corrida se reutiliza (caché de §10) y solo se clasifica lo nuevo.
7. **`make corrida-fgr`** corre la misma corrida en el momento, para probarla sin esperar al horario.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| 32 búsquedas por estado en cada corrida | 96 al día, muchas repetidas. Benji eligió una nacional (§9.1). |
| Tablas nuevas `scheduled_runs` y `run_articles` (plan §4.7) | Una corrida ya es una búsqueda: `searches` y `search_results` guardan lo mismo. Una columna `trigger` evita duplicar el modelo. |
| Ventana «desde la corrida anterior», a la hora exacta | Las búsquedas trabajan por días y los RSS no siempre traen la hora. Con hoy y ayer no se pierde nada, y lo repetido no se paga. |
| SearchApi en las automáticas | Medido el 25/10: 27 de sus 30 notas ya venían en el RSS. Gastaría créditos en repetidas. |
| APScheduler u otro proceso | El reloj de Celery ya corre (ADR-0022). |

## Consecuencias

- **Costo:** 0 créditos; solo la IA para las notas nuevas (~0.0002 USD por nota leída y ~0.00002 por nota clasificada).
- **Si la PC está apagada a la hora de la corrida, esa corrida no ocurre.** La siguiente cubre hoy y ayer. Se resuelve de fondo con la migración a Proxmox (F12.9).
- **El reporte de cada corrida queda listo** en disco y se puede volver a pedir desde Explorar. Los envíos (WhatsApp o correo) quedan para la F12.11.

## Ventana por horas (28/10/2026)

**Antes**, cada corrida pedía «hoy y ayer» por días completos (`AUTOMATIC_WINDOW_DAYS=1`). La de las 07:00 del 28/10 trajo 356 notas: de sus 160 relevantes, 140 eran del día anterior y solo 23 eran nuevas. Benji: «debe buscar estrictamente en el día vigente, y únicamente en el lapso de horas desde que se hizo la última corrida».

**Ahora**:
- **Cada corrida cubre desde la anterior** (`run_window`, `app/domain/schedule.py`):
  - 07:00, de las 23:00 de ayer a las 07:00;
  - 15:00, de 07:00 a 15:00;
  - 23:00, de 15:00 a 23:00.
- **Aunque la anterior no haya terminado**, cubre solo su periodo (corregido el 28/10/2026, tarde). Antes cubría desde la última que sí terminó, hasta un día atrás, y podía traer notas de otro periodo. Benji: «únicamente deben de salir las noticias del periodo anterior al periodo actual… es lo más importante». Lo que se pierda si una corrida falla se recupera corriendo esa corrida a mano (`make corrida-fgr`), no estirando la siguiente. `AUTOMATIC_WINDOW_DAYS` ya no existe.
- **El filtro se aplica después de consultar.** A los buscadores se les piden los días que toca la ventana (solo entienden días), y el pipeline descarta lo publicado fuera de las horas antes de guardarlo y antes de la IA. Las notas sin fecha de publicación tampoco entran, porque no se puede saber si ya salieron.
- **Se guarda la ventana.** `searches.window_start` y `window_end` (migración 0033) llevan las horas, y la pantalla y el PDF las muestran («27 oct 23:00 – 28 oct 07:00»).
- **Es estricto, por decisión de Benji.** `AUTOMATIC_WINDOW_MARGIN_MINUTES` (0) permite mirar unos minutos antes si se nota que se pierden notas que los buscadores muestran tarde.

**Medido** con los datos reales de la corrida de las 07:00 del 28/10: con la ventana habría traído 73 notas en lugar de 356, y 22 relevantes en lugar de 160.
