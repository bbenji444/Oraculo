# ADR-0103: Cuándo y cómo se extraen las entidades de las noticias

- **Estado:** aceptado (21/10/2026, plan de la 9.4 aprobado por Benji).
- **Fase:** 9.4.

## Contexto

El tablero de investigación necesita las personas, organizaciones, lugares y vehículos de las noticias, cada uno con su estatus legal según la nota y una cita que lo pruebe (ADR-0104 y 0105).

El plan de fases (§9.7) proponía pedirlas en la misma llamada que hoy resume cada nota de cada búsqueda. Mediciones con la base real (21/10/2026, gpt-6-luna a 0.10/0.50 USD por millón):

- Resumir una nota cuesta de 0.0003 a 0.0011 USD.
- Una búsqueda trae de 20 a 40 notas, y casi ninguna termina en un caso.

## Decisión

1. **Las entidades se extraen solo de las notas que entran a un caso,** en una llamada aparte con su propio prompt versionado (`entities_v1.md`, `EntityExtractorPort`). Al agregar la nota se encola sola en el worker; las que ya estaban o fallaron se piden con «Analizar con IA».
2. **Se leen una vez por nota y versión de prompt** (`entity_extractions`). Si la nota entra a otro caso, se reutiliza sin volver a pagar.
3. **Freno contra lo inventado:** la cita debe aparecer literal en el texto que leyó la IA, y el nombre (o un alias) también. Lo demás se descarta con su motivo, para medir a la IA. La cita guardada es la del texto, no la de la IA.
4. **Agrupación dentro del caso:** las menciones con el mismo nombre normalizado y tipo forman una sola sugerencia. Nada se agrupa entre casos, ni con lo ya confirmado o descartado. Unir nombres parecidos queda para la 9.5.
5. **Texto:** se usa el cuerpo extraído y recortado. Si ya se borró a los 30 días (ADR-0015), se usan título y fragmento del medio, marcados `title_snippet`. El resumen propio nunca sirve como evidencia.
6. **Tope:** 200 notas leídas por caso.

## Alternativas consideradas

- **En la misma llamada del enriquecimiento:**
  - Pros: una sola llamada por nota.
  - Contras:
    - guarda nombres de personas de toda nota buscada, relevante o no, en contra de la minimización (§9.10);
    - encarece cada búsqueda;
    - las notas ya resumidas necesitarían de todos modos una pasada aparte.
- **Agrupar entre casos:**
  - Se descarta: unir automáticamente a dos personas distintas con el mismo nombre es inaceptable (§9.8).

## Consecuencias

- **Costo real del punto de control** (5 notas reales, 21/10/2026): 0.00376 USD, de 0.00048 a 0.00107 USD por nota. Entre 10 y 30 entidades por nota; 1 de 99 descartada porque su cita no estaba en la nota.
- **Al confirmar una entidad,** las menciones nuevas de esa persona llegan como otra sugerencia, que la 9.5 propondrá unir.
- **La base guarda nombres de personas señaladas en noticias,** solo de notas que alguien eligió investigar.
