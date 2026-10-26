# ADR-0029: Categoría de cada noticia (el delito), en un catálogo en la base y con una llamada aparte de la IA

- **Estado:** Aceptado
- **Fecha:** 25 de octubre de 2026
- **Fase:** F12.4
- **Decide:** Benji («que me catalogue por tipo de noticia… la IA fracciona en conceptos, y si hay alguno distinto, a "otros"»; «de momento haz que funcione; después, con base en un análisis de resultados, catalogamos las categorías más frecuentes con colores y símbolos»)

## Contexto

El reporte y la línea de tiempo de la FGR necesitan saber de qué trata cada nota. La lista provisional del plan (§4.4) tiene 13 categorías de delito más «Otros».

La IA ya devuelve un `event_type`, pero en la búsqueda FGR del 24/10/2026 (189 notas) ese campo describe **qué hizo la autoridad** («investigación» 21, «detención» 9, «cateo», «sentencia», «amparo») y está vacío en 53 notas. Es otra dimensión: la acción, no el delito.

## Decisión

1. **Catálogo en la base** (`categories`, migración 0026), sembrado con la lista provisional.
   - Cada categoría lleva una descripción para la IA.
   - Una sola es la de respaldo («Otros», `is_other`, con índice único parcial).
   - `color` y `symbol` nacen vacíos: se definen después, con datos.
2. **Una categoría por nota** en `articles.category_id` (con índice), más:
   - `category_raw`: la etiqueta libre de la IA, para el análisis de frecuencias de después;
   - `category_version`: la versión del prompt.
3. **`event_type` no cambia**: sigue siendo la acción de la autoridad. Las dos dimensiones se muestran por separado.
4. **Llamada aparte de la IA**, por lotes de hasta 25 notas, con título y resumen (o fragmento). No va dentro del enriquecimiento, porque cambiar `enrich_v2` invalidaría la caché (`reusable_for`) y se volverían a pagar completas todas las notas ya procesadas.
5. **Lo que no encaja va a «Otros»**: también una categoría que la IA invente. Su etiqueta queda en `category_raw`.
6. **Nunca se borra nada:** reclasificar solo reemplaza la categoría de la nota.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Agregar la categoría al prompt de enriquecimiento | Invalida la caché de todas las notas ya pagadas y obliga a releer artículos completos. |
| Reglas fijas a partir de `event_type` | `event_type` es la acción, no el delito, y viene vacío en el 28 % de las notas. |
| Usar los conceptos como categorías | Los conceptos son lo que se busca (FGR); las categorías son lo que se encontró. |
| Lista fija en el código | Benji quiere afinarla con datos; en la base se cambia sin desplegar. |
| Varias categorías por nota | Más complejo de mostrar y de contar. Se elige la principal; si hace falta, se cambia a una tabla de relación. |

## Consecuencias

- **Costo** (gpt-6-luna): ~0.0005 USD por lote de 25 notas, unos 3 centavos para las 1,450 notas guardadas.
- **El reporte y la línea de tiempo** pueden contar y filtrar por categoría.
- **Pendiente, con datos reales:**
  - qué categorías se quedan, se juntan o se agregan, según `category_raw` y las frecuencias;
  - sus colores y símbolos.

## Ajuste: «Seguridad nacional (traición a la patria)» (26/10/2026)

**Contexto.** En las corridas FGR del 26/10, el 72 % de las notas quedaba en «Otros» (169 de 235 a las 15:00), y así el filtro por categoría casi no servía. La etiqueta libre que más repetía la IA era «traición a la patria»: 90 notas del caso Jáuregui y de los agentes extranjeros en Chihuahua.

**Decisión** (aprobada por Benji):

- La migración 0029 agrega «Seguridad nacional (traición a la patria)» justo antes de «Otros».
- El prompt `classify_v4` añade una regla: lo que rodea a un caso penal (protestas, cartas, audiencias, caravanas o declaraciones sobre un acusado) va en la categoría del delito, no en «Otros».
- Al cambiar la versión del prompt se vuelven a clasificar todas las notas, con respaldo previo.

**Consecuencias.**

- La IA vuelve a decir también quién actúa en cada nota. Esas reglas no cambian, pero la respuesta puede variar un poco, así que se miden las relevantes para la FGR antes y después.
- Siguen pendientes las demás categorías definitivas y sus colores. Por ahora el color sale de la paleta provisional, por id.
