# ADR-0107: Revisión en bloque y fuerza de los vínculos de un caso

- **Estado:** aceptado (11/11/2026, plan de «casos claros» aprobado por Benji con las decisiones D1 a D4).
- **Fase:** F12 (mejora de la Fase 9).

## Contexto

Benji pidió (11/11/2026) que la parte de Casos se entienda mejor, que haya forma de **seleccionar todo** en lugar de confirmar una cosa a la vez, y que los vínculos **sirvan para algo**.

Medición con el caso real «Chuy» (3 notas, 36 entidades):

- Había **170 vínculos sugeridos** «aparecen juntas». Con tres notas casi todo aparece junto a todo: «California — Colorado», «@FGRMexico — FBI».
- Cada entidad y cada vínculo se confirmaba con su propio botón.
- La IA ya marca en cada mención si la entidad **participa en el hecho** (`role = event`) o **solo se nombra** (`mentioned`), pero ese dato no se usaba.
- Si se pide que las dos entidades participen en el hecho de una misma nota, quedan **30 de 170**, y son las que importan: «Jesús González Peñuelas — camioneta Ford», «Secretaría de Marina — Cártel de Guasave».

## Decisión

1. **Revisión en bloque** (`POST /cases/{id}/entities/review` y `POST /cases/{id}/relationships/review`).
   - Es la misma revisión firmada de siempre (ADR-0104), solo que para varios elementos: se confirma o se descarta, nada regresa a «sugerido».
   - **Todo o nada:** el caso de uso valida todo antes de escribir y el repositorio guarda en una sola transacción.
   - **La bitácora no cambia de forma:** cada elemento deja su propio `entity.confirmed`, `entity.discarded`, `relationship.confirmed` o `relationship.discarded`, con `"bulk": true` para distinguirlo.
   - **Tope de 500 por petición** (`BULK_REVIEW_MAX_ITEMS`): cubre un caso de unas diez notas sin dejar una transacción abierta mucho tiempo.
   - Lo que ya estaba así no se toca ni repite la bitácora; la respuesta dice `{changed, unchanged}`.
2. **D1 — Personas confirmadas en bloque:** cada una queda con el estatus legal que se ve en su renglón (el que sugirió la IA o el que eligió el analista); si la nota no lo dice, «mencionado». Se valida igual que una por una: nunca «culpable».
3. **D2 — Las fusiones siguen par por par.** Unir a dos personas distintas es el error más grave (ADR-0104); cada par se mira lado a lado.
4. **D3 — La fuerza de un vínculo se calcula al leer** (`link_strength`, como ADR-0106):
   - **Fuerte:** las dos participan en el hecho de al menos una nota del caso, o lo dibujó una persona.
   - **Débil:** solo se nombran en las mismas notas.
   - Cada nota de la evidencia dice si las dos participan (`same_event`), y el vínculo trae `same_event_count`, `strength`, `strength_label` y `reason` («participan en el mismo hecho en 2 notas (aparecen juntas en 3)»).
   - La lista ordena primero los fuertes. **No cambia** el tipo (`appears_with`), la confianza de la 9.5 (D6), lo ya guardado ni el muro.
5. **D4 — Nada se esconde para siempre:** en la pantalla los débiles van en un grupo plegado; siguen ahí para quien los quiera revisar.

## Alternativas consideradas

- **Derivar `same_event` como un tipo nuevo de vínculo:**
  - Pros: el muro podría dibujarlo distinto sin más cambios.
  - Contras: cambia la llave (`entity_a`, `entity_b`, `type`) de los vínculos calculados; lo ya revisado como `appears_with` quedaría duplicado con un `same_event` nuevo.
- **Bajar la confianza de los débiles en lugar de clasificarlos:**
  - Pros: un solo número.
  - Contras: mezcla dos ideas (cuántas notas y qué papel tienen en ellas) y rompe la regla D6 de la 9.5, que ya se documentó a los analistas.
- **Una sola entrada de bitácora por revisión en bloque:**
  - Pros: menos filas.
  - Contras: ya no se puede preguntar «¿quién confirmó a esta persona?» con la misma consulta de siempre.
- **Fusiones en bloque:** descartadas por D2.

## Consecuencias

- **Lo que se gana:** revisar un caso pasa de decenas de clics a unos pocos, sin perder la firma ni la bitácora por elemento; los vínculos útiles salen primero y se explican solos.
- **Lo que cuesta:** la lista de vínculos lee también el rol de cada mención (`bool_or(role = 'event')` por grupo y nota); con el caso real tarda lo mismo.
- **Depende de la IA:** si marca mal quién participa en el hecho, un vínculo útil puede quedar como débil. Por eso la fuerza solo ordena y agrupa; nunca esconde ni descarta.
- **El muro** recibe los campos nuevos en sus aristas (mismo esquema que `/relationships`), pero todavía no los usa.
