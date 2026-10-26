# ADR-0026: Historias: el mismo hecho en varios medios se agrupa comparando con la primera nota

- **Estado:** Aceptado
- **Fecha:** 24 de octubre de 2026
- **Fase:** F12.1c (nivel 3 de duplicados del ADR-0025)
- **Decide:** Benji (aprobó el plan de F12.1c; pidió «no saturarnos de información… sin descartar información importante» y tarjetas con chevron ▸ / ▼)

## Contexto

Después de los niveles 1 y 2 (ADR-0025) ya no se guarda dos veces la misma nota. Pero el mismo **hecho** contado por varios medios sigue llenando la lista: la balacera de Iztapalapa del 23/10 aparecía en 15 tarjetas. Borrar esas notas sería perder información: qué medios lo publicaron, a qué hora, con qué datos.

Calibración con las 1,450 notas reales de `articles` (24/10/2026):

| Forma de agrupar | Historias | Notas agrupadas | Tamaño máximo | Juicio |
|---|---|---|---|---|
| En cadena (A~B y B~C ⇒ A, B y C juntas) | 120 | 549 | 61 | Arrastra temas enteros («caso Jáuregui», «Día de Muertos») |
| **Contra la primera nota de la historia** | **172** | **491** | 15 | Los ejemplos revisados son el mismo hecho |

## Decisión

1. **Nada se borra.** `articles.story_id` guarda el id de la primera nota de la historia (migración 0024, con índice); una nota sola queda en `NULL`.
2. **La regla** está en `app/domain/stories.py`, sin librerías; las similitudes se inyectan desde `adapters/text/similarity.py`:
   - **Limpiar el título:** se quitan los segmentos finales que nombran al medio («– Periódico Zócalo | Noticias de Saltillo…»).
   - **Comparar con la primera nota:** una nota entra a una historia si se parece a esa nota, con alguno de estos dos criterios:
     - títulos con parecido ≥ 0.70 (`fuzz.ratio`);
     - parecido por palabras ≥ 0.60 (`fuzz.token_set_ratio`) **más** una señal: el mismo lugar principal con clave INEGI; o 2 palabras poco comunes en común (≤ 8 títulos de la ventana); o el mismo estado y 1 palabra poco común. Las claves de país (`MEX`) no cuentan como lugar.
   - **Ventana:** a ≤ 2 días de la última nota de la historia y a ≤ 3 días de la primera.
   - **Varias opciones:** si una nota cabe en varias historias, gana la más antigua.
3. **Cuándo se agrupa:**
   - **Al cerrar cada búsqueda** (`RunSearch._close`, también en las corridas automáticas), las notas nuevas se comparan con las de su ventana de fechas. Si agrupar falla, la búsqueda no se cae: el error va a `processing_errors`.
   - **Lo ya guardado:** `make agrupar-historias` recalcula todo desde cero. Sin opciones solo muestra conteos y 5 historias; con `--aplicar` pide «si».
4. **En el monitor:** una tarjeta por historia con «▸ +N medios», que al desplegarse cambia a «▼» y muestra el resto. El globo sigue mostrando cada nota.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Agrupar en cadena (componentes conexos) | Grupos de 61 notas que mezclan hechos distintos del mismo tema. |
| Solo parecido de títulos ≥ 0.70 | Deja fuera titulares redactados distinto del mismo hecho («Dos muertos por ataque en Ermita Iztapalapa» / «Balacera en Iztapalapa deja dos muertos»). |
| Embeddings de OpenAI | Mejor con títulos muy distintos, pero cuesta y depende de una API; la regla gratuita ya da grupos limpios. Queda como mejora si se necesita, con aprobación aparte. |
| Comparar resúmenes de la IA | Solo existen en las notas enriquecidas (928 de 1,450); se puede sumar después como señal. |

## Consecuencias

- La lista pasa de 1,450 a ~1,131 tarjetas (−22 %) sin perder ninguna nota.
- **El error esperado:** un mismo hecho partido en dos historias (la balacera tiene una segunda historia de 5 notas). Es preferible a juntar hechos distintos.
- **Notas que llegan tarde:** se comparan con las historias de su fecha. `make agrupar-historias --aplicar` lo recalcula todo si hiciera falta.
- **Reporte:** el reporte (F12.10) podrá contar hechos, no solo notas, con `story_id`.

## Ajuste: casos que dominan la ventana (26/10/2026)

En la corrida FGR de las 07:00 del 26/10 había 162 notas en 94 hechos, y 41 de esos hechos eran del caso Jáuregui. La misma vinculación a proceso quedaba partida en unas 12 historias. La causa: cuando un caso domina, sus palabras («JAUREGUI», «TRAICION», «PATRIA») aparecen en decenas de títulos y dejan de contar como «poco comunes», así que la regla no encontraba señal.

Cambios:

1. **Regla fuerte.** Basta un parecido por palabras de 0.75 o más (`SAME_STORY_STRONG_TOKEN_SIMILARITY`) con 3 palabras en común o más, aunque sean comunes. Medido: los pares del mismo hecho daban de 0.75 a 0.91, con 3 a 6 palabras.
2. **Gana la historia más parecida, no la más antigua.** Con la regla fuerte, la derrama de Coparmex caía en «CDMX espera 500 mil visitantes».
3. **El mismo lugar pide dos palabras en común** (`PLACE_SHARED_TOKENS`). Con una sola («MUERTOS»), las notas de Día de Muertos en CDMX se juntaban entre sí.

Resultado al reagrupar las 1,660 notas:

- **Todas las notas:** de 1,242 a 1,232 tarjetas.
- **La corrida FGR:** de 94 a 87 hechos.
- **El caso Jáuregui:** de 41 a 34 hechos.
- **Mejoras:** la vinculación de Axe Ceremonia queda en una historia de 10 notas, y el choque del Metrobús, el desfile y la derrama de Día de Muertos también quedan juntos.
- **Retroceso conocido:** la muerte del actor Carlos Miguel queda en 3 o 4 historias en lugar de una de 5. Sus títulos se parecen poco entre sí.

Los 34 hechos del caso Jáuregui que quedan son, en buena parte, hechos distintos (la carta, la caravana, las protestas, las columnas). Esa saturación se atiende en la pantalla, agrupando por caso (ADR-0032).
