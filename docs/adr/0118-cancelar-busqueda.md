# ADR-0118: Cancelar una búsqueda que corre

- **Estado:** propuesto (19/11/2026; revisado el mismo día tras una revisión independiente del cambio).
- **Fase:** F12.

## Contexto

Benji, 19/11/2026: «tiene que estar la opción de cancelar búsqueda por si me equivoqué en algo o necesito regresar y editar».

Antes de este cambio no había forma de detener una búsqueda:

- **Pantalla:** mientras corría, la consola solo mostraba el avance y el botón de minimizar. «Ajustar consulta» aparecía hasta que terminaba.
- **Base:** la regla `searches_status_known` (migración 0011) solo aceptaba `pending`, `running`, `completed`, `partial` y `failed`.
- **Worker:** `RunSearch.run` corría de principio a fin sin revisar nada. El id de la tarea de Celery no se guarda, así que no se podía matar la tarea desde la API.

Una búsqueda de varios días con la IA tarda minutos. Equivocarse de región o de fechas significaba esperar a que terminara y pagar todo.

## Decisión

1. **Estado nuevo `cancelled`** (`SearchStatus.CANCELLED`), que cuenta como terminado (`is_finished`). La migración 0050 solo amplía la regla de la base: ninguna fila cambia.
2. **Cancelar es marcar la fila, no matar la tarea.** `POST /searches/{id}/cancel` pasa la búsqueda a `cancelled` si sigue en `pending` o `running`, con la bitácora `search.cancelled` en la misma transacción. `finished_at` lo pone el worker al detenerse: mientras siga vacío, todavía no guarda lo gastado y la pantalla sigue leyendo la búsqueda (`isSettled`).
   - Si ya terminó, responde `409`.
   - Solo puede cancelar quien la lanzó, y solo búsquedas manuales (`can_cancel_search`). Una corrida automática del monitor FGR alimenta el reporte y los envíos programados de todos (ADR-0031). Cancelarla dejaría ese horario sin reporte.
3. **El worker se detiene solo.** `RunSearch` revisa `is_cancelled` en dos lugares:
   - antes de cada cambio de etapa (`_progress`);
   - en la IA, antes de mandar cada nota. Es la etapa larga y la que cuesta: cada nota tarda segundos.

   Las notas que ya estaban con la IA se dejan terminar para contar sus tokens.

   No se revisa desde «filter», la etapa en que ya se ligan las notas: la IA está pagada, y cortar a mitad del cierre dejaría notas ligadas en una búsqueda con 0 notas. Si la cancelan en ese momento, queda cancelada con lo que encontró.

   Después cierra con `_close_cancelled`, que guarda:
   - los créditos de las consultas que ya salieron, que se cobran igual;
   - los tokens y el costo de la IA;
   - las consultas ejecutadas, para la bitácora `search.finished` con `estado: cancelled` (CLAUDE.md §8);
   - `results_count` en 0 y el resumen «Cancelada por quien la lanzó.».
4. **No se liga ninguna nota a la búsqueda cancelada.** Lo que la IA ya leyó se ubica y se guarda antes de cerrar (`_save_enriched`, lo mismo que hace la etapa de ubicar). Así se queda en el índice y la siguiente búsqueda lo reutiliza sin pagarlo otra vez, que es justo el caso de «me equivoqué y la lanzo de nuevo».
5. **La cancelación gana siempre.**
   - `start` y `fail` no tocan una búsqueda cancelada.
   - `finish` conserva `cancelled` si la cancelaron después de la última revisión del pipeline: guarda lo gastado y la bitácora dice `cancelled`. `RunSearch` lo vuelve a leer al final para que su resumen diga lo mismo que la base.
   - Por eso `make reubicar` no reprocesa una búsqueda cancelada: se detiene en la primera revisión.
6. **Pantalla.**
   - Mientras corre el barrido, la consola del Centro de mando muestra «Cancelar búsqueda» (`CancelSearchButton`). No sale en las corridas automáticas.
   - Al cancelar, la consola vuelve a «Ajustar consulta», como el botón del mismo nombre, con lo que se pidió. La vuelta va en la mutación (`useCancelSearch(onCancelled)`) y no en `mutate()`, porque el sondeo puede ver «cancelled» antes que la respuesta y quitar el botón. En la búsqueda rápida, la barra arranca con el texto que se escribió (`QuickSearchBar.initialText`).
   - El historial la marca «Cancelada». «Misiones recientes» no la ofrece.
   - El aviso es «Búsqueda cancelada: ajusta la consulta y lánzala de nuevo».
   - No hay ventana de confirmación: cancelar no borra nada, y la búsqueda se vuelve a lanzar desde la misma consola.

## Alternativas consideradas

- **Matar la tarea de Celery (`revoke(terminate=True)`).**
  - Habría que guardar el id de la tarea.
  - Matar el proceso a media escritura deja la fila en `running` y sin bitácora de lo gastado.
  - Se descartó.
- **Revisar solo entre etapas.** Más simple, pero la IA es la etapa larga: con 150 notas, cancelar a la mitad seguiría pagando las 75 restantes.
- **Borrar la búsqueda al cancelar.** Se pierde la bitácora de lo gastado y el historial. Para quitarla ya existe «Quitar del historial» (reversible).
- **Dejar que cancele un superusuario la de otra persona.** No se pidió, y la de otra persona normal ni se ve (RLS, ADR-0042). Se puede agregar después.

## Consecuencias

- Cada revisión es una consulta por id a `searches`, una por etapa y una por nota de la IA: unas cientos por búsqueda, contra la llave primaria.
- La cancelación no es instantánea. Una consulta a un proveedor o una nota que la IA ya está leyendo terminan; el worker se detiene unos segundos después. La pantalla no espera: vuelve a la consola en cuanto la API responde.
- Bajar la migración 0050 convierte las búsquedas canceladas en `failed`: es un cambio de datos, se hace con respaldo (`make db-dump`).
- El estado nuevo llega a la API (`status: "cancelled"`). Quien integre el monitor por API debe tratarlo como terminado (`docs/api.md`).
