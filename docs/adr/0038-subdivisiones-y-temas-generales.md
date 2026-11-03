# ADR-0038: Subdivisiones editables y temas generales

- **Estado:** Aceptado (02/11/2026).
- **Fecha:** 2 de noviembre de 2026
- **Fase:** F12
- **Decide:** Benji. Lo que pidió el 02/11/2026:
  - ver y editar **todas** las subdivisiones, porque el filtro solo mostraba las 8 que salían en las notas;
  - poder buscar cada subdivisión sola, «solo homicidios en general, sin la FGR»;
  - una ventana al centro del Centro de mando con dos bloques: «Fiscalía General de la República» con sus subdivisiones, y «Temas generales».

  Sobre la FGR más una subdivisión: «si hago esas búsquedas en específico tiene que tener la condición de traer ambas palabras».

## Contexto

Las 15 categorías de la tabla `categories` (ADR-0029) son las subdivisiones de la FGR. La IA las usa para clasificar cada nota por delito **después** de buscar. No había forma de:

- verlas todas ni editarlas desde la pantalla;
- **buscar** por una de ellas, porque una categoría no tiene palabras clave; solo tiene una descripción para la IA.

Los conceptos (ADR-0009) sí tienen palabras clave, y de ellas salen las consultas a cada fuente. En F12.6 se retiraron todos menos el de la FGR (ADR-0030).

## Decisión

1. **Cada subdivisión tiene un tema general, que es un concepto.** La columna nueva `concepts.category_id` liga el concepto con su categoría. Un índice único parcial impide dos temas vivos para la misma subdivisión. El tema se llama y se pinta igual que su subdivisión. Sus palabras clave y exclusiones se editan como las de cualquier concepto, en `PATCH /concepts/{id}`. «Otros» no tiene tema, porque no hay palabras que lo definan.
2. **Un tema se busca solo o junto con la FGR:**
   - **Solo** («Homicidio»): es un concepto más y sus notas son las que traen sus palabras.
   - **FGR + subdivisión** («FGR · Homicidio»): la búsqueda manda `category_ids`. Las palabras del tema se copian en `search_concepts.topic_terms` y cada consulta lleva **un segundo grupo** que también debe aparecer: `(FGR OR "Fiscalía General de la República") (homicidio OR asesinato …)`. Así se cumple «ambas palabras». Las exclusiones del tema se suman a las del concepto.
     - El índice local exige además que aparezca una palabra del tema (`text_norm ~ :topic`).
     - En Google News RSS el grupo va en cada consulta partida por día.
     - Si las palabras del tema no caben con la palabra clave más larga, se reparten en grupos y cada grupo se cruza con todas las palabras clave. No se pierde ninguna combinación.
   - A un tema general no se le agrega otra subdivisión: ya es una. Pedir subdivisiones sin un concepto como la FGR es un error claro.
3. **Las subdivisiones se editan en pantalla** con `PATCH /categories/{id}`: nombre, descripción (lo que lee la IA), color y si está prendida.
   - Su tema toma el mismo nombre y se prende o apaga con ella.
   - «Otros» no se apaga: es a donde va lo que no encaja.
   - Cada edición queda en la bitácora (`category.updated`, con antes y después).
   - `GET /categories?include_inactive=true` devuelve también las apagadas.
4. **Los temas los siembra `make seed`** desde `backend/app/seed/temas.json`. Crea solo los que falten y nunca pisa una edición. Las 14 listas de palabras se le muestran a Benji antes de guardarlas en la base (CLAUDE.md §2.6).
5. **La corrida automática no cambia.** Sigue buscando solo el concepto FGR por su nombre (ADR-0031). `make retirar-conceptos` ya no retira los temas.

## Alternativas consideradas

- **Palabras clave en la tabla `categories`.** Duplicaría lo que ya hacen los conceptos: validación, vista previa de consultas, bitácora y editor. Se descartó.
- **Filtrar por la categoría que asignó la IA después de buscar.** Así no se buscan notas nuevas del tema: solo se filtran las que trajo la FGR. Tampoco sirve para buscar «sin la FGR». Ese filtro sigue existiendo en el expediente.
- **FGR + subdivisión como un OR** (cualquiera de las palabras). Traería todo lo de homicidios aunque no tenga que ver con la FGR. Benji pidió que vengan ambas.

## Consecuencias

- **Costo por SearchApi** (cuando el switch está prendido; las fuentes gratis siguen en 0). Medido el 02/11/2026 con el límite de 32 palabras:
  - un tema solo cuesta 1 o 2 créditos por semana;
  - con la FGR, hasta 3.

  La estimación lo muestra antes de lanzar.
- **El historial muestra la subdivisión:** `ConceptRef.subdivision_ids`, y la pantalla dice «FGR · Homicidio».
- Editar una subdivisión no reclasifica las notas ya clasificadas: vale para las siguientes.
- Hay 14 conceptos nuevos en `/concepts`, todos con `category_id`.
