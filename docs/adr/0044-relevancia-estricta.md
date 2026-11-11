# ADR-0044: Relevancia estricta: el concepto debe ser el asunto principal

- **Estado:** aceptada
- **Fecha:** 2026-11-11
- **Fase:** F12
- **Relacionadas:** ADR-0030 (regla «FGR federal»), ADR-0015 (lectura con IA)

## Contexto

Una búsqueda de «Desaparición de personas + Homicidio» en Cuauhtémoc mostraba notas basura en el mapa. Benji pidió (11/11/2026): «sé mucho más estricto, que solo nos dé la información que realmente queremos».

Se revisaron los juicios guardados de la IA (`enrich_v3`):

| Nota | Qué es en realidad | Juicio con v3 |
|---|---|---|
| «Manifestaciones hoy martes 10… ¿dónde habrá marchas?» | Agenda de marchas | Homicidio, sí (0.98) |
| «Estudiantes protestan contra prohibición de celulares…» | Lista de marchas | Homicidio, sí (0.85) |
| «Hallan restos humanos y piezas prehispánicas en Buenavista» | Hallazgo arqueológico | Desaparición, sí (0.98) |
| «Cuauhtémoc Cárdenas, entre la democracia y el caudillismo» | Análisis político | Homicidio, sí (0.75) |

**Causa:** v3 consideraba relevante una nota si el tema aparecía **mencionado en cualquier parte**. Una agenda de 15 marchas con una por feminicidio contaba como «Homicidio». Es el mismo error de fondo que ADR-0030 resolvió para la FGR: mencionar no es tratar.

Además, 2 de 25 notas fallaban: la respuesta llegaba cortada porque las agendas enumeran decenas de lugares y se pasaban del tope de 2048 tokens. Esas notas se quedaban sin resumen ni juicio.

## Decisión

1. **Prompt `enrich_v4`.**
   - Es relevante solo si el concepto es el **asunto principal**, con una prueba rápida: si se quita esa parte, ¿la nota sigue casi igual? Entonces no lo es.
   - No cuentan las agendas o listas de muchos temas (marchas, bloqueos, «lo que pasó hoy», tránsito, clima, efemérides), ni las menciones de pasada.
   - Sí cuentan:
     - el activismo de víctimas y colectivos cuando es el asunto principal;
     - en conceptos que son una institución, cualquier acción oficial de ella (acuerdos, cooperación, reuniones de trabajo).
   - «Si dudas, no es relevante.» El puntaje queda en 0.8 o más solo si es claramente principal y en menos de 0.6 si es dudoso.
   - Máximo 12 lugares por nota.
2. **Filtro de confianza** (`MIN_RELEVANCE_SCORE = 0.6`). Un «sí» de la IA con menos de 0.6 no cuenta. Se aplica al leer (`effective_relevance` y `KEEPS_RELEVANCE`), así que vale también para las búsquedas pasadas.
3. **Tope de la respuesta:** de 2048 a 3072 tokens. Solo se cobra lo que de verdad se escribe.

Al cambiar de versión, la caché (`reusable_for`) vuelve a leer cada nota la primera vez que aparece en una búsqueda nueva: cuesta lo mismo que una búsqueda normal. Los juicios viejos se quedan en las búsquedas pasadas, salvo por el filtro de confianza.

## Evidencia (prueba real del 11/11/2026, US$0.0168 en total)

- **Primera ronda (23 notas):** de 14 notas que la búsqueda marcaba como relevantes, quedaron 5, todas correctas.
  - Se quitaron 8 notas basura: 5 agendas de marchas, el hallazgo arqueológico y 2 notas sobre Cuauhtémoc Cárdenas.
  - Se quitaron 2 dudosas.
  - No apareció ninguna nueva.
- **Segunda ronda, con el ajuste de activismo e instituciones (11 notas):**
  - las 2 dudosas volvieron (madres buscadoras con 0.95; FGR + ONU con 0.9);
  - las 2 que fallaban por respuesta cortada se procesaron sin error y se quitaron bien (eran agendas);
  - la basura siguió fuera y lo bueno siguió dentro.

## Alternativas consideradas

- **Solo el filtro de confianza.** No basta: v3 daba 0.85–0.98 a la basura.
- **Exigir que la categoría coincida con la subdivisión.** La categoría también se equivocaba (la agenda de marchas salió «Homicidio»).
- **Una lista de palabras prohibidas** («marchas», «bloqueos»). Quitaría marchas que sí son del tema, como las de madres buscadoras.
- **Volver a juzgar todas las notas guardadas.** Costaría y el texto de las notas viejas ya se borró (se guarda 30 días). Las búsquedas nuevas ya usan v4.

## Consecuencias

- Las búsquedas nuevas traen menos notas y más limpias. Puede quitarse alguna nota de interés que la IA vea como secundaria; se puede revisar con «No relevantes».
- En las búsquedas pasadas, las notas con un «sí» de menos de 0.6 pasan a «No relevantes».
- Los conteos del historial pueden bajar un poco al leerse con el filtro.
