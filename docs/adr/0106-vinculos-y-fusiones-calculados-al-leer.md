# ADR-0106: Vínculos y sugerencias de fusión calculados al leer

- **Estado:** aceptado (21/10/2026, plan de la 9.5 aprobado por Benji).
- **Fase:** 9.5.

## Contexto

La 9.5 agrega dos cosas a las entidades de un caso (plan de fases §9.6 y §9.8):

- **Vínculos:** «aparecen juntas» cuando dos entidades salen en la misma nota, y los que dibuja el analista.
- **Resolución:** sugerir qué entidades son la misma y dejar que una persona las una (ADR-0104).

Lo que se ve del caso cambia con muchas acciones: confirmar o descartar una entidad, unir o separar, agregar o quitar una nota, y que la IA lea una nota nueva. Mediciones con el caso real (21/10/2026): 83 entidades y 1,055 pares posibles del mismo tipo.

## Decisión

1. **Sugerencias de fusión calculadas al leer.**
   - Se sugiere un par del mismo caso y tipo, no unido ni descartado, si tiene el mismo nombre de comparación, un nombre o alias en común (contando lo ya unido) o trigramas ≥ 0.9.
   - Esto amplía el plan, que pedía «trigramas ≥ 0.9 **y** alias en común». Tomado literal perdía «Micky Hair», «FGJ CDMX» y los «N». Con la unión salen 27 pares en el caso real.
   - Solo se guarda «No son la misma» (`entity_merge_dismissals`, migración 0022), y vale para los grupos enteros.
2. **Unir solo escribe `merged_into`.**
   - Menciones, alias y vínculos no se mueven: las lecturas resuelven cada grupo con un CTE recursivo acotado al caso.
   - «Separar» borra ese `merged_into`, y se deshace exacto.
   - Si una de las dos está confirmada, esa es la que queda.
   - «Separar menciones» pasa menciones propias a una sugerencia nueva.
3. **Vínculos por coocurrencia calculados al leer.**
   - Solo entre entidades **confirmadas**: con sugeridas, cada nota daría cientos de pares de ruido.
   - Confianza: 0.5 con una nota compartida, 0.7 con dos y 0.9 con tres o más.
   - Se guardan en `relationships` solo al confirmarlos o descartarlos. Lo descartado no vuelve.
4. **Lo que dibuja el analista nace confirmado**, con origen `human`, confianza 1 y su firma. No es una propuesta (ADR-0104 aplica a lo que propone la máquina).
5. **Rutas por llave.** Un sugerido por coocurrencia no tiene id, así que se revisa con `POST /relationships/confirm|discard {case_id, entity_a, entity_b, type}` en lugar de `/relationships/{id}/confirm` del plan.
6. **El parecido se compara en el dominio, no en SQL.**
   - La base da los trigramas de cada entidad (`show_trgm`), y `merge_reasons` aplica el filtro por prefijo (AllPairs).
   - Con 3,000 entidades sintéticas, el SQL tardaba 52.6 s. PostgreSQL no usa el índice GIN en una tabla así de chica y compara todos contra todos.
   - En el dominio da los mismos 21 resultados en 353 ms. Una prueba lo compara contra `similarity()`.

## Alternativas consideradas

- **Guardar coocurrencias y sugerencias en tablas y refrescarlas:**
  - Pros: lecturas triviales.
  - Contras: hay que refrescar en seis lugares (confirmar, descartar, unir, separar, agregar y quitar nota). Un refresco olvidado deja vínculos con notas que ya no están en el caso.
- **Unir moviendo menciones y vínculos a la que queda:**
  - Pros: lecturas sin CTE.
  - Contras: deshacer exige recordar qué era de quién. Una fusión equivocada de personas es el error más grave aquí.
- **Coocurrencia también entre sugeridas:**
  - Se descarta por el ruido: hay 10 a 30 entidades por nota, y solo lo confirmado llega al muro.

## Consecuencias

- **Lo que se gana:** lo que se ve siempre está al día y cada decisión se puede deshacer con firma en la bitácora (`entity.merged`, `.unmerged`, `.split`, `.merge_dismissed`, `relationship.*`).
- **Lo que cuesta:** cada lectura recalcula. Con 3,000 entidades sintéticas:
  - sugerencias: 353 ms;
  - lista de entidades: 170 ms;
  - conteos: 15 ms;
  - vínculos entre 150 confirmadas: 38 ms.

  Si un caso crece mucho más, el siguiente paso es guardar los trigramas por entidad.
- **Las comillas** se corrigieron en la misma sub-fase (migración 0021): «Eduardo “N”» y «Eduardo N» ya son el mismo nombre de comparación.
- **Vínculos propuestos por la IA** (origen `llm`) quedan fuera: pedirlos es otro prompt con otro costo.
