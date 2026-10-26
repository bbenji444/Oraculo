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

## Ajuste: a la izquierda, con desglose y sin repetir (26/10/2026)

Benji pidió la cronología del lado izquierdo y con más información al elegir un hecho, sin repetir lo que ya se ve.

- **Va en el panel izquierdo**, debajo de la búsqueda, en el lugar de la lista de noticias. «☰ Lista» y «◷ Cronología» cambian entre las dos. El lado derecho queda libre para el globo.
- **Desglose al elegir un hecho:** qué medios lo publicaron, a qué hora y entre qué horas («Lo publicaron 8 medios entre 08:32 y 13:46»), con el titular de cada medio cuando es distinto y su link.
- **No repite lo que dice la ficha del globo.** Un primer intento ponía también el resumen, la categoría y quién actúa, pero eso ya sale en la ficha que se abre al mismo tiempo: era leer lo mismo dos veces.
- Al elegir una nota desde el globo, solo se desplaza la cronología. Antes, `scrollIntoView` también movía la pantalla entera y dejaba una franja negra abajo; el contenedor de Explorar ahora usa `overflow: clip`.

**Globo:**

- **Aureola cian muy tenue y un brillo del Sol** asomándose por el borde, arriba a la izquierda. Son dos capas CSS detrás del mapa, sin luz en el globo ni división entre el día y la noche, y se apagan al acercarse (zoom 3 a 4.5).
- MapLibre no da el contorno del globo en pantalla. Se calcula proyectando anillos de puntos alrededor del centro, porque con la cámara inclinada el borde ya no queda donde dice la fórmula del radio.
- **Acercamiento al lugar de los hechos:**
  - al volar a una nota: localidad a 14.5 (se ven las calles), municipio a 11.5, estado a 7 y país a 5, con inclinación de 45°;
  - al elegir una región: el tope sube a 15 para localidad y a 12.5 para municipio;
  - un grupo de notas encimadas se abre 1.5 niveles más cerca.

## Temas: un caso no tapa la cronología (26/10/2026)

Incluso con las historias mejoradas (ADR-0026), la corrida FGR del 26/10 tenía 27 hechos distintos del caso Jáuregui: la carta, la caravana, las audiencias y las columnas. Eran 27 renglones seguidos.

- **Tema:** un nombre propio que sale en al menos 5 hechos (`THEME_MIN_ITEMS`) se vuelve un bloque «TEMA · Jáuregui · 27 hechos · 61 notas · del 25 al 26 oct», con lo último que pasó. Un nombre propio es una palabra con mayúscula inicial que no abre el título. El bloque se despliega con sus hechos y el día y la hora de cada uno, y se abre solo si la nota elegida está adentro.
- **No cuentan:**
  - los lugares (estados y lugares de las notas), porque para eso está el filtro por estado;
  - las palabras de oficio («Fiscalía», «Gobierno»…).
- **Sin IA ni costo.** Se calcula en el navegador (`themes.ts`). Cada hecho va al tema más grande que nombra, aunque su título venga en mayúsculas.
- **Resultado en esa corrida:** de 65 renglones a 31.
- **Riesgo:** una persona que aparece en hechos sin relación, como la presidenta, puede formar un tema que mezcle asuntos. Se llama «tema» y no «caso» por eso. Si estorba, se agrega a `NOT_A_THEME`.
