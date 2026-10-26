# ADR-0032: Línea del tiempo: barras por fecha de publicación, orden por fecha del hecho

- **Estado:** Aceptado
- **Fecha:** 26 de octubre de 2026
- **Fase:** F12.7
- **Decide:** Benji (plan F12 §4.6: «muy importante: la representación con líneas del tiempo… orden de fecha y hora de cada noticia, visualmente atractivo, tanto en el monitor como en el PDF»; «para el orden de investigación manda la fecha del hecho cuando existe»)

## Contexto

Cada nota trae cuándo se **publicó** y, a veces, cuándo **ocurrió** el hecho (`event_date`, que la IA deduce en los avances de casos viejos).

En la corrida FGR del 26/10/2026 había notas publicadas ese día de hechos de noviembre de 2025 o de febrero. Con la fecha del hecho en el eje, este se estiraba a un año y las barras de los dos días buscados se volvían invisibles.

## Decisión

1. **Barras y tramos por fecha de publicación**, en hora de la CDMX: por hora si la búsqueda cubre hasta 3 días, por día si cubre más. Muestran los picos de cobertura del periodo, con los 3 más altos resaltados en cian. Elegir una barra filtra ese tramo.
2. **La tira de notas se ordena por fecha del hecho** si la hay (◆) y, si no, por la de publicación (●). Un botón cambia a «cuándo se publicó».
3. **Filtros por categoría** (el delito, ADR-0029) **y por estado** (la clave INEGI de la ubicación principal).
4. **Un solo filtro para todo:** se aplica a la misma lista que usan el globo y la lista de noticias (`ExplorePage`). Así el mapa, la lista y la línea del tiempo muestran siempre las mismas notas.
5. Elegir una nota en la tira es lo mismo que elegirla en el globo: el mapa vuela hacia ella.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Todo por fecha del hecho | Un avance de hoy de un caso de 2025 estira el eje a meses y esconde los picos del día. |
| Todo por fecha de publicación | El analista pierde el orden en que ocurrieron los hechos, que es lo que pide la investigación. |
| Una librería de gráficas | Unas barras y una tira no la necesitan; se dibuja con elementos HTML accesibles (cada barra es un botón con su conteo). |

## Consecuencias

- **El PDF (F12.10) usa la misma lógica** para su gráfica de la línea del tiempo.
- **Pendiente:** colores por categoría en las barras, cuando se definan los colores (ADR-0029).

## Rediseño del 26/10/2026

A pedido de Benji («más clara, menos estorbosa, que se lleve con el mundo, sin noticias duplicadas»):

- **Sin caja de fondo:** solo un degradado para leerla sobre el globo, una curva de densidad que brilla y el número de cada pico.
- **Un punto por historia, no por nota:** el mismo hecho en varios medios (`story_id`, ADR-0026) es un solo punto, más grande cuantos más medios lo publicaron. Se apilan hasta 4 por tramo y el resto se cuenta con «+N».
- **La tira de tarjetas se reemplaza por una ficha flotante** al pasar el mouse (hora, título, medio, categoría, lugar y, si es de antes, cuándo ocurrió el hecho). Un clic vuela el globo hacia la nota.
- **La lista de noticias del panel izquierdo empieza oculta**, porque la línea del tiempo la reemplaza. «☰ Lista» la vuelve a mostrar.
- **Los puntos van por fecha de publicación**, igual que la curva, y la fecha del hecho se dice en la ficha. Se quitó el botón de orden, que confundía.

## Segundo rediseño: cronología vertical (26/10/2026)

Benji no se convenció con la línea horizontal y eligió, entre tres propuestas, una **cronología vertical**:

- Es un panel delgado a la derecha, como un feed en vivo. El globo queda libre en el centro.
- **Arriba:** cuántos hechos hay, una curva pequeña de notas publicadas por hora (los picos brillan; un clic filtra esa hora) y los filtros por categoría y estado.
- **La línea:** vertical y luminosa, con la hora a la izquierda y cada hecho a la derecha, del más reciente al más viejo, agrupados por día.
  - El mismo hecho en varios medios es una sola entrada («+7 medios»).
  - Si el hecho es de antes, la entrada lo dice.
  - Un clic vuela el globo hacia la nota.
- El vidrio usa los tonos de OSINT: borde cian tenue y desenfoque de 14 px.
- La lista del panel izquierdo sigue oculta y vuelve con «☰ Lista».

**Globo:** se quitó la luz del Sol en su posición real, porque marcaba demasiado la división entre el día y la noche. El día y la noche los elige el analista con su botón. Se conservan los ajustes de color de las imágenes de la NASA.
