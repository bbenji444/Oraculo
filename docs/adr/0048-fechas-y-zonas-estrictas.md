# ADR-0048: Fechas y zonas estrictas en las búsquedas

- **Estado:** aceptada
- **Fecha:** 2026-11-11
- **Fase:** F12
- **Relacionadas:** ADR-0041 (notas fuera de la región), ADR-0031 (ventana de las corridas automáticas)

## Contexto

Benji, 11/11/2026: al buscar «hoy» llegaban notas de ayer. «Si es 11 de noviembre y le doy nada más buscar hoy, muy súper estrictamente solamente tienen que venir los parámetros que estoy buscando… No nos tiene que dar ninguna nota del día 12… Y súper estricto de las zonas que yo estoy buscando.»

Había dos causas:

1. **Fechas.** Las búsquedas manuales le pedían a cada fuente los días elegidos, pero no revisaban la fecha de publicación de lo que llegaba. Google News y el índice local devuelven «las últimas 24 horas» o días vecinos. Solo las corridas automáticas filtraban por su ventana de horas.
2. **Zonas.** Una nota sin lugar identificado contaba como «sin ubicación» y aparecía en la búsqueda, aunque se hubiera pedido un estado o un municipio (ADR-0041 solo sacaba las de fuera).

## Decisión

1. **Fechas: cada búsqueda tiene su ventana estricta** (`strict_window`):
   - corrida automática: su ventana de horas, como antes;
   - búsqueda manual: los días elegidos completos en hora de la Ciudad de México, de las 00:00 del primero a las 00:00 del día siguiente al último (sin incluir). «Hoy» el 11/11 es del 11/11 00:00 al 12/11 00:00.

   Se aplica igual que en las corridas automáticas:
   - lo publicado fuera, o sin fecha, se descarta antes de guardarlo y antes de pagar a la IA;
   - se revisa otra vez con la fecha ya guardada (una nota vieja puede volver con otra fecha);
   - un hecho anterior al primer día tampoco cuenta.
2. **Zonas: sin lugar no cuenta en una región menor a un país.** Si se buscó un estado, municipio o localidad, una nota sin ubicación queda **fuera** (`in_region = false`): no se puede asegurar que pasó ahí. En búsquedas de todo el país sigue como antes: cuenta, salvo que el medio sea de otro país (ADR-0041).

3. **«Últimos N días» cuentan hoy** (corrección del mismo 11/11, tras publicar los puntos 1 y 2: «Hoy» seguía trayendo notas del 10).
   - **Causa:** `DateWindow.last_days` restaba `N` días completos. «Hoy» (N = 1) se volvía «de ayer a hoy» («10 – 11 nov · 2 días»), y «7 días» eran 8. El filtro estricto del punto 1 funcionaba, pero con un periodo mal armado.
   - **Ahora:** «Hoy» es solo hoy y «7 días» son hoy y los 6 anteriores (`today - (N - 1)`).

## Alternativas consideradas

- **Dejar las notas sin fecha.** Pueden ser de cualquier día; Benji pidió estricto.
- **También en todo el país, quitar las notas sin lugar.** Muchas notas nacionales de la FGR no dicen dónde pasó, y el monitor automático las perdería. Se queda solo para regiones menores.

## Consecuencias

- Las búsquedas manuales traen menos notas, pero todas del periodo y de la zona pedidos. Además se paga menos IA, porque lo de fuera ya no se lee.
- Lo de las búsquedas pasadas no cambia: las fechas se filtran al buscar y la zona al cerrar o con `make reubicar`.
- Una nota local que no menciona ningún lugar se pierde en una búsqueda de un estado. Sigue guardada y se ve con el filtro «Fuera de la región» (`in_region=false`).
