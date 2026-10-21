# Fase 9 — Tablero de investigación ("el muro")

Pega este prompt en Claude Code (Opus 5.5, esfuerzo xhigh, modo plan) para arrancar la fase.
Requisito: `docs/PLAN_FASES_9-10-11.md` está en el repositorio y la rama está limpia.
Esta fase es grande: trabájala **una sub-fase por sesión** (9.1 a 9.7). Al cerrar cada una, `/clear` y vuelve a pegar este prompt indicando la sub-fase siguiente.

```
Vamos a construir la Fase 9 del proyecto: el tablero de investigación ("el muro").

CONTEXTO
Lee completos docs/PLAN_FASES_9-10-11.md (Parte II) y repasa CLAUDE.md y docs/ESPECIFICACION.md. El plan amplía la especificación; las reglas de trabajo de CLAUDE.md siguen vigentes. La extracción de entidades va sobre la pasada del LLM que ya existe (OpenAI), no en un paso aparte.

ANTES DE PLANEAR
Demuéstrame que entendiste, en no más de 15 líneas, en español:
- el principio rector (entidades source-agnostic) y por qué hace escalable el proyecto;
- cómo conviven hoy las entidades de noticias con el enchufe futuro a las bases reales (tabla external_links, reservada y vacía);
- qué es lo más riesgoso de esta fase según tú.
Si ves contradicciones con lo ya construido en las Fases 0-8, o algo que no te convence del plan, dímelo ahora con tu propuesta.

REGLAS INNEGOCIABLES DE ESTA FASE
- Toda entidad o vínculo que proponga el LLM entra como SUGERIDO; nada se confirma ni se fusiona solo (ADR-0104).
- Las personas NUNCA se fusionan automáticamente a nivel global.
- El estatus legal refleja lo que dice la noticia (señalado, detenido, víctima...), NUNCA "culpable".
- La extracción toma solo lo que dice el texto; no infiere ni cruza datos entre noticias ni con otras bases.
- external_links se crea, se documenta y se deja VACÍA; ninguna lógica de la Fase 9 la escribe ni la lee.
- Toda columna de filtro o paginación lleva su índice en la misma migración.
- Cada acción sobre casos y entidades, incluida VER un caso, queda en la bitácora de auditoría.
- El rendimiento es criterio de aceptación: el muro debe sostener 60 fps al rotar y animar en un equipo de oficina.

PLAN DE TRABAJO
Vamos sub-fase por sub-fase, en el orden de la tabla 9.11 del plan:
9.1 Decisión del motor visual (ADR-0102) con prototipo de nodos, arcos de luz y cámara; medir fps reales.
9.2 Modelo de datos y migraciones (incluida external_links reservada).
9.3 CRUD de casos y agregar ítems (historia H9.1).
9.4 Extracción de entidades por LLM + confirmación humana (historia H9.2).
9.5 Vínculos (coocurrencia + manuales) y resolución de entidades.
9.6 El muro sobre el globo: nodos, arcos, cámara, panel lateral, constelación (historia H9.3).
9.7 Línea de tiempo, notas del investigador, auditoría de visualización (historias H9.4 y H9.5).

EMPEZAMOS POR LA SUB-FASE 9.1
1. Revisa cómo están hechos hoy el globo y el pipeline del LLM, y dime si algo hay que ajustar para encajar la Fase 9 sin romper lo existente.
2. Construye un prototipo mínimo que dibuje sobre el globo actual unos nodos y arcos de luz con una cámara que vuele y orbite, para medir fps. Prueba primero potenciar MapLibre con una capa de efectos encima; si lo ves necesario, compáralo con migrar a un motor con más control 3D. Muéstrame los fps reales de cada opción.
3. Preséntame el plan de la 9.1 con archivos, commits con su mensaje exacto (CLAUDE.md 4.2), riesgos y cómo medirás los 60 fps. Espera mi aprobación antes de escribir código.
4. Trabaja en la rama feat/f9-1-motor-visual. Al terminar, entrégame el ADR-0102 con tu recomendación y la evidencia de fps, el resumen de cierre de sub-fase, y no avances a la 9.2.

Antes de procesar noticias reales con el LLM para extraer entidades (sub-fase 9.4), muéstrame 5 ejemplos reales (entidades propuestas con su estatus legal y su evidence_span) y espera confirmación.
```
