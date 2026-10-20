# Fase 11 — Capas avanzadas y modo cine

Arranca esta fase solo cuando la Fase 10 esté cerrada. Pégalo en Claude Code (Opus 5.5, xhigh, modo plan).
Requisito: `docs/PLAN_FASES_9-10-11.md` en el repositorio.
Naturaleza: **desarrollo y evaluación**. Trabájala por bloques (satélites, clima, modos visuales, orquestador), un bloque por sesión.

```
Vamos a construir la Fase 11: capas avanzadas y modo cine. Es una fase de desarrollo y evaluación.

CONTEXTO
Lee docs/PLAN_FASES_9-10-11.md (Parte IV) y repasa CLAUDE.md. Esta fase se apoya en el puerto LiveLayerPort de la Fase 10 y en el muro de la Fase 9. Mantén una sola aplicación coherente; God's Eye View (MIT) sigue siendo solo referencia de implementación.

ANTES DE PLANEAR
En no más de 12 líneas, explícame:
- cómo encaja el "orquestador" que permite capturar un dato vivo (un sismo, una embarcación) dentro de un caso del muro, convirtiéndolo en evidencia con su marca de tiempo y procedencia;
- cómo implementarías los modos visuales (visión nocturna, térmico, vista cabina) como post-procesado sobre el globo sin romper el rendimiento;
- qué parte de esta fase es la de mayor riesgo.

REGLAS DE ESTA FASE
- Por cada fuente nueva, deja en el código y en un ADR la nota de su licencia como DATO (sin afirmar uso comercial): CelesTrak es de origen gubernamental de EE. UU. con citación solicitada; NOAA GFS es dominio público.
- CÁMARAS: God's Eye View trae cámaras de California (Caltrans) y Londres (TfL), que NO cubren México. NO implementes cámaras hasta tener una fuente legítima para México (C5/C4 estatales). Déjalo documentado como pendiente y dímelo si crees haber encontrado una fuente válida.
- Los modos visuales son polish: no deben bajar el globo de 60 fps. Si un efecto no se sostiene, se degrada con elegancia.
- Al revisar la postura de producción (fuera de esta fase), recuerda que OpenSky (nivel gratuito, no comercial) y el mapa de cables submarinos de TeleGeography (CC BY-NC-SA, no comercial) necesitan revisión legal. Solo déjalo anotado; no estorba el desarrollo.

PLAN DE TRABAJO (un bloque por sesión)
11.1 SATÉLITES en órbita (CelesTrak, TLE/SGP4) sobre el globo.
11.2 CLIMA: viento y tormentas (NOAA GFS).
11.3 MODOS VISUALES: visión nocturna (filtro verde), térmico/FLIR y vista cabina (primera persona), como shaders de post-procesado.
11.4 ORQUESTADOR: capturar un dato vivo dentro de un caso del muro, con su marca de tiempo y procedencia.
11.5 CÁMARAS: solo si se consigue una fuente legítima para México; si no, queda documentado como pendiente.

EMPEZAMOS POR EL BLOQUE QUE YO TE INDIQUE
1. Dime en qué bloque empezamos (por defecto, 11.1 satélites).
2. Consulta la documentación oficial vigente de la fuente del bloque y cítala. No inventes parámetros.
3. Preséntame el plan: diseño, archivos, commits con mensaje exacto, riesgos y cómo lo verificaré. Espera mi aprobación.
4. Trabaja en la rama feat/f11-N-<descripcion>. Al cerrar, muéstrame el bloque funcionando, entrégame el resumen de sub-fase y el ADR con la nota de licencia cuando aplique. No avances al siguiente bloque sin mi aprobación.
```
