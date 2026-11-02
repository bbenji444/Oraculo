# ADR-0033: Reporte PDF con el lenguaje visual de Oráculo: expediente, categorías, línea del tiempo y Estado ▸ Categoría ▸ Noticias

- **Estado:** Aceptado
- **Fecha:** 26 de octubre de 2026
- **Fase:** F12.10
- **Decide:** Benji (plan F12 §0 y §6: «un reporte mucho más dinámico… muy visual… muy formal»; «lo único que le gustó a mis jefes fue la representación visual de México con porcentajes, me pidieron más cosas así»; «las noticias con flecha de despliegue tipo chevron»; el 26/10/2026: «quiero que armes los pdf»)

## Contexto

El reporte de la F7 (ADR-0018) era un documento claro y sobrio. Le faltaba:

- la clasificación por delito (F12.4) y quién actúa (F12.5);
- la línea del tiempo (F12.7);
- la división de las noticias por estado;
- el lenguaje visual de Oráculo.

Como referencia de diseño se usó el expediente de persona de Oráculo 2.0 que Benji compartió. De él se tomó **solo la forma**, nunca su contenido:

- número de expediente;
- banda de confidencialidad;
- insignias de confianza;
- fechas en mayúsculas.

Los colores y tipografías salen de OSINT Oráculo (F12.7a).

## Decisión

1. **Portada Oráculo de hoja completa:**
   - fondo `#050505` con una red de nodos en cian, dibujada con una semilla fija por expediente: no hace falta ninguna imagen externa;
   - el número de expediente (`EXP-FGR-20261025-2300` en las corridas automáticas);
   - título en Orbitron y las cifras clave;
   - la banda «USO INTERNO · CONFIDENCIAL».
2. **Cada página interior lleva el expediente** en el encabezado, «USO INTERNO · CONFIDENCIAL», la fecha de emisión y el número de página. Las páginas interiores siguen en blanco para que se impriman bien.
3. **Panorama:** cifras, resumen ejecutivo y datos clave (ahora también el delito más frecuente) y **tarjetas por categoría** con su estado principal y las etiquetas libres más repetidas. Lo que viene de la IA lleva la insignia «IA · INFERENCIA».
4. **Se conserva el mapa de México con porcentajes**, la tabla por estado (ahora con %) y los medios. Se agregan **barras apiladas por categoría** en cada estado.
5. **Línea del tiempo:**
   - las barras usan la fecha de publicación, por hora o por día, en hora de la CDMX (ADR-0032);
   - los 3 picos van resaltados, cada uno con la nota que lo explica.
6. **Noticias por Estado ▸ Categoría ▸ Nota**, numeradas de corrido:
   - Estados y categorías generan **marcadores plegables** en el panel del lector de PDF (`bookmark-state: closed`). Es el «chevron» que funciona en cualquier lector, sin JavaScript.
   - Cada nota lleva sus insignias: categoría, quién actúa y confianza (ALTA, MEDIA o BAJA según el puntaje de relevancia de la IA).
7. **Fuentes incluidas:** Orbitron (de OSINT, OFL) para títulos y cifras, y Noto Sans para el texto. Se quitan los emojis de títulos y resúmenes: ninguna de las dos fuentes los tiene y salían como cuadros. Los chevrons usan «›», que Noto Sans sí tiene.
8. **Las corridas automáticas (F12.8) usan este mismo reporte**, y se sigue pudiendo pedir desde Explorar.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Secciones desplegables dentro de la página (JavaScript en el PDF) | Solo funcionan en Adobe Reader y no se imprimen. Los marcadores plegables funcionan en cualquier lector. |
| Mapa coloreado por categoría dominante | Requiere otro mapa estático; las barras apiladas por estado dicen lo mismo y caben junto al mapa con %. Queda como mejora. |
| Imagen de portada de OSINT | Una imagen corporativa no sirve de portada para cualquier reporte; la red generada se ve igual y no depende de archivos externos. |
| Fuentes del expediente de referencia (IBM Plex Mono, Spectral) | Habría que descargarlas. Orbitron y Noto Sans ya estaban, y Orbitron es la tipografía técnica de Oráculo. |

## Consecuencias

- **Tamaño:** el reporte de la primera corrida automática ocupa 26 páginas (104 notas) y ~265 KB.
- **Colores de las categorías:** son provisionales, hasta que se definan con datos (ADR-0029). Si una categoría trae `color`, se usa ese.
- **Pendiente:**
  - mapa por categoría dominante;
  - envío del reporte por WhatsApp o correo (F12.11).

## Ajuste: una ficha por hecho (26/10/2026)

El reporte de la corrida de las 15:00 del 26/10 traía 143 fichas en 33 páginas. Varias eran el mismo hecho contado por varios medios, con resúmenes casi iguales («Estoy bien y muy fuerte», de Jáuregui, en tres medios).

Ahora cada hecho (historia, ADR-0026) es **una ficha**: la de la nota que se publicó primero, con una línea «También lo publicaron (N)» que da el medio, la hora y el link de las demás, sin repetir el resumen. El encabezado de cada estado dice «37 hechos · 76 notas · 54 %». El porcentaje sigue contando notas, igual que el mapa. Ese reporte quedó en 76 fichas y 22 páginas.

## Ajuste: menos listado, más gráficas (28/10/2026)

Benji: «a mí de nada me sirve tener 100, 200 noticias en un listado interminable porque nadie lo va a ver. Prefiero resúmenes, gráficas, datos importantes… que sí aparezcan las noticias de manera individual, pero no quiero saturarlo».

- **Notas por categoría:** dona con el total al centro y una tabla con barra de color, número, porcentaje y el estado donde más salen. Antes eran tarjetas.
- **Línea del tiempo por hora, de colores por categoría** (`TimeBar.segments`), como los puntos del globo, con su leyenda.
- **Cronología de hechos destacados** (`highlights`). Son los 8 hechos que más medios publicaron (`MAX_HIGHLIGHTS`); entre iguales, el más relevante y luego el más reciente. Van en orden de hora, en una línea vertical con un nodo del color de su categoría. Cada uno lleva su resumen, sus insignias y cuántos medios lo publicaron. Son las únicas notas con resumen.
- **Índice de noticias:**
  - Estado ▸ Categoría ▸ un renglón por hecho, con número, hora, título con link, medio y «+N» medios;
  - tiene un tope de 40 hechos (`MAX_LISTED_FACTS`, `limit_groups`); lo demás se consulta en el monitor o en el CSV;
  - la numeración no cambia, para que las citas sigan valiendo.

**Alternativa descartada:** quitar el índice. Se descartó porque Benji pidió que las noticias sigan apareciendo una por una.

## Ajuste: las preguntas del analista (28/10/2026, noche)

Benji pidió ver el reporte «desde un punto humano: curioso, preguntón… que le gusta tener todo claro y organizado», con respuestas «no escritas, sino de forma representativa», y una tipografía más formal.

**Decisión.** Cada bloque abre con una pregunta numerada. Debajo va una línea de conclusión, calculada sin IA (`questions.py`), y luego su gráfica:

| # | Pregunta | Respuesta visual |
|---|---|---|
| 01 | ¿Qué pasó en este periodo? | Cifras, resumen ejecutivo y datos clave |
| 02 | ¿Qué es lo más importante? | Los 3 hechos más publicados, en tarjetas con su resumen y sus medios |
| 03 | ¿De qué delitos se trata? | Dona y tabla por categoría |
| 04 | ¿Qué tipo de actuación hubo? | Barras: sentencias, procesos, detenciones, aseguramientos, investigaciones, denuncias |
| 05 | ¿Dónde pasó? | Mapa y tabla por estado |
| 06 | ¿Qué pasa en cada estado? | Fichas de los 6 estados con más notas: delito, actuación y hecho más publicado |
| 07 | ¿Cuándo pasó? | Barras por hora de colores por categoría, con picos |
| 08 | ¿Cómo se desarrollaron los hechos? | Cronología con marcas de hora y una tarjeta por hecho |
| 09 | ¿Qué tan confiable es la información? | Confianza de la IA, precisión del lugar y medios |

Al final va el índice por estado, con una franja de colores por estado y un filo de color por renglón.

**El tipo de actuación** sale del tipo de hecho que anotó la IA al leer la nota (`event_type`) y, si ahí no hay nada reconocible, del título. Se agrupa por raíces de palabras (detien-, asegur-, vincul-, sentencia…). Se rotula «Clasificación automática».

**Tipografía.** Títulos, cifras e insignias pasan de Orbitron a Noto Sans: Orbitron se veía de videojuego y no daba formalidad. Orbitron queda solo en la marca «ORÁCULO» de la portada.

**Sin repetir.** Los 3 hechos más importantes llevan su resumen en «¿Qué es lo más importante?». En la cronología solo se marcan como «Hecho destacado nº N».

**Resultado** con la corrida de las 07:00 del 28/10/2026: 10 páginas, sin hojas casi vacías.

**Alternativa descartada:** que la IA escriba las conclusiones de cada pregunta. Costaría una llamada más por reporte, y una cifra mal redactada por la IA sería más grave que una frase sencilla calculada.

## Ajuste: tipografía de informe formal (30/10/2026)

Benji: «pon texto justificado en el PDF y con unas tipografías más pro». Se usa la pareja serif para leer y sans para títulos de los informes formales, toda de la familia Noto: tiene la Ñ, todos los acentos y la misma licencia OFL. Las fuentes y sus SHA-256 están en `backend/app/adapters/reports/fonts/README.md`.

- **Noto Serif**, justificada y con división de palabras en español, en el texto de lectura. WeasyPrint divide con `pyphen`, que ya instala.
- **Noto Serif negrita** en los titulares y el título de la portada.
- **Noto Sans seminegrita** en las preguntas, los títulos, las cifras y las etiquetas. Las tablas, las listas y los renglones cortos siguen alineados a la izquierda, porque justificar un renglón corto abre huecos.
- Las direcciones web no se dividen (`.nohyphen`).
- Orbitron queda solo en la marca «ORÁCULO».

### Cambio: IBM Plex en lugar de Noto Serif (30/10/2026)

Benji: «una tipografía más pro, que no parezca hecha en un documento de Word». Noto Serif se veía de procesador de textos. Ahora el reporte va en IBM Plex:

- **Sans:** el texto, justificado y con división de palabras;
- **Sans Condensed:** títulos, preguntas, titulares y cifras;
- **Mono:** horas, expediente y numeración.

El conjunto da la apariencia de un informe técnico. Son 8 archivos WOFF2 que pesan 165 KB en total; Noto Sans queda de respaldo para las letras fuera del subconjunto latino. Orbitron sigue solo en la marca.

### Cambio: Exo 2 e Inter, como la interfaz (30/10/2026, noche)

Benji: «algo que se vea más moderno pero tampoco tan exagerado, algo acorde al sistema». El reporte deja IBM Plex y usa la misma pareja que el monitor:

- **Exo 2:** títulos, preguntas, titulares y cifras;
- **Inter:** el texto justificado, y también horas y numeración, con cifras tabulares.

Así el PDF se reconoce como parte del mismo sistema. Orbitron sigue solo en la marca.

## Ajuste: «¿Qué cambió?» y Barlow (02/11/2026)

- **«¿Qué cambió desde la corrida anterior?»** reemplaza a «¿Qué tipo de actuación hubo?». Benji pidió «otra que aporte un valor mayor»: quien recibe un reporte cada 8 horas quiere saber qué se movió. La sección trae:
  - la conclusión, por ejemplo «Esta corrida trae 48 notas (+25). Sube Homicidio (+7). Focos nuevos: Baja California, Chihuahua y Oaxaca»;
  - el total de antes frente al de ahora;
  - los 5 delitos y los 5 estados que más se movieron, con la barra de antes y la de ahora;
  - los focos nuevos y los estados que se quedaron sin notas.

  Solo sale en las corridas automáticas, que tienen una anterior (`ReportData.previous_articles`). Las preguntas se numeran solas, así no queda un hueco en las búsquedas manuales. El tipo de actuación sigue en las fichas por estado y en los hechos destacados.
- **Barlow.** Benji la eligió entre tres muestras del mismo reporte: Barlow Semi Condensed en títulos y cifras, y Barlow en el texto. Ver `fonts/README.md`.
