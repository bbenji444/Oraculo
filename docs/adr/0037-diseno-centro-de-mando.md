# ADR-0037: Diseño «Centro de mando» para la búsqueda (diseño 3)

- **Estado:** Aceptado (27/10/2026). Benji lo eligió («se ve muy, muy bien») y desde entonces es el diseño principal. El diseño 2, con la columna, queda con `?clasico` en la URL y con la etiqueta `diseno-consola-tactica-v2`.
- **Fecha:** 27 de octubre de 2026
- **Fase:** F12
- **Decide:** Benji. Lo que pidió el 27/10/2026: «una nueva estructura o acomode de la interfaz de búsqueda… súper novedoso… muy, muy, muy personalizada la búsqueda… que la gente sienta que está en un sistema de millones de pesos». Pidió mantener el mismo globo, los mismos estilos, las mismas letras y los mismos botones.

## Contexto

El diseño 2 (ADR-0036) le gusta a Benji y quedó guardado con la etiqueta `diseno-consola-tactica`. Su búsqueda es un formulario en una columna a la izquierda: región, conceptos, fechas, fuentes, costo y botón, uno debajo del otro. Funciona, pero se lee como cualquier formulario.

Benji quiere comparar ese diseño con otro acomodo de la búsqueda, sin perder el actual.

## Decisión

1. **La búsqueda se escribe como una orden.** Abajo al centro va una consola de misión con una frase que se lee de corrido:

   > Rastrear **[01 FGR]** en **[02 Jalisco]** durante **[03 los últimos 7 días]** vía **[04 2 fuentes gratis]**

   Cada parte se toca y sube una tarjeta con los mismos controles del diseño 2. Las partes que faltan brillan en ámbar.
2. **La consola cambia con la misión:**
   - para armar la misión: la frase, el costo con cifras que corren y el botón «Iniciar barrido», con aro de carga y onda expansiva;
   - buscando: un riel con las 8 etapas del pipeline, la etapa en curso descifrándose, el porcentaje, un cronómetro y una bitácora con los números que ya se conocen;
   - con resultados: un renglón con la misión activa, «Ajustar misión» y «Nueva misión»;
   - minimizada: una pastilla.
3. **El globo es el escenario.** Flota entre el encabezado y la consola, con el zoom ajustado para que quepa completo (`fitZoom`, `map/framing.ts`):
   - mientras se busca, un radar lo barre;
   - al terminar, aparece un letrero grande: «BARRIDO COMPLETO · 56 notas».
4. **Los resultados van en un expediente a la derecha.** El globo se corre a la izquierda. El expediente tiene:
   - un título que se descifra;
   - cuatro cifras: relevantes, estados, créditos y costo de la IA;
   - una barra con las categorías que más salen;
   - la misma cronología o lista del diseño 2, y las descargas.

   Se oculta con «›» y el globo se recentra. Los controles del mapa se recorren con el expediente.
5. **Personalizada.** Dentro de la consola hay tres apoyos:
   - las misiones recientes y la última corrida automática, para reabrirlas sin costo;
   - el reloj de la Ciudad de México y la cuenta regresiva a la próxima corrida automática (07:00, 15:00 y 23:00);
   - atajos: «/» abre la región y Esc cierra la tarjeta.
6. **Las mismas reglas de búsqueda.** El diseño 3 lanza con `useSearchLauncher`, la lógica que se sacó del panel del diseño 2. El tope de créditos, la llave de la IA y las fuentes funcionan igual en los dos.
7. **Las mismas reglas visuales que el ADR-0036.** Solo se anima `transform`, `opacity` y sombras pequeñas. No se usa `backdrop-filter`. Con «reducir animaciones», nada se mueve. Los estilos van en `src/styles/mando.css` y solo aparecen con `?mando`.

## Alternativas consideradas

- **Un asistente paso a paso** («¿Dónde? → ¿Qué? → ¿Cuándo?»). Se descartó porque son cuatro pantallas para algo que hoy es un clic. El analista que repite búsquedas perdería tiempo.
- **Una barra de comandos estilo Spotlight**, con texto libre. Se descartó porque habría que interpretar lo escrito, y eso invita a errores. La frase con partes tocables se ve igual de directa sin adivinar nada.
- **Reemplazar el diseño 2.** Se descartó porque Benji quiere compararlos. Los dos conviven y la URL decide.

## Consecuencias

- El diseño 2 no cambia en pantalla. Para compartir código hubo tres refactors:
  - `useSearchLauncher`;
  - `MyCasesToggle`;
  - `ConceptChips` y `DateRange` exportados.

  Además, el globo acepta márgenes abajo y arriba (`insetBottom`, `clearHeader`).
- Desde que se aceptó se abre sin nada en la URL (`?mando` sigue valiendo). Para el diseño 2 se abre `http://localhost:8080/?clasico#/explorar`.
- **Riesgo:** en pantallas bajas (menos de ~650 px de alto), la consola y el expediente dejan poco lugar al globo. El zoom tiene un tope inferior (`GLOBE_FIT_MIN_ZOOM`) para que no se vuelva una canica.
- La prueba de humo del flujo principal (H1) recorre este diseño. La del diseño 2 corre con `?clasico`.

## Ajustes al aceptarlo (27/10/2026)

Benji pidió estos ajustes al elegirlo:

- **Sin naranja en la consola.** «No va acorde a los demás colores». Lo que falta elegir late en cian con borde punteado. Los créditos de pago van en violeta y los avisos en rojo.
- **Consola más chica, pero igual de clara.** La letra de la frase, los márgenes y el botón son más chicos. El ancho máximo bajó de 64 a 54 rem.
- **Fondo de vidrio.** «Que no sea tan azul… que se pueda ver la parte de atrás». La consola, sus tarjetas y el resumen del expediente son translúcidos (`.mando-glass`), con un brillo en la orilla de arriba. Siguen sin desenfoque, por la tarjeta Intel.
- **Lista de noticias más grande y clara.** «Se ve una parte muy pequeña de las noticias». Se hicieron tres cambios:
  - el expediente pasa de 26 a 30 rem;
  - el resumen de arriba se pliega aparte («▴») a un renglón con sus cifras;
  - la cronología y la lista se ven 10 % más grandes (`zoom` en `.mando-feed`), sin tocar los componentes que comparten los dos diseños.
- **Más color y animación en el resumen.** Cada cifra es una lámina de vidrio de su color: cian, verde, violeta y azul cielo. Un brillo cruza cada lámina a destiempo, la barra de categorías brilla y un haz recorre el resumen al llegar los resultados. La barra de categorías ya no usa ámbar.

## Segundos ajustes (27/10/2026, tarde)

- **«Consulta» en lugar de «misión».** «Misión» le sonaba poco profesional a Benji. La frase sigue igual («Rastrear… en… durante… vía…»), pero los botones dicen «Ajustar consulta» y «Nueva consulta», y la consola, «Consulta activa».
- **Más noticias a la vista.** Benji veía solo 3. Ahora son unas 6 o 7 en 920 px de alto:
  - el resumen es más bajo y se puede dejar plegado; la preferencia se recuerda;
  - dentro del expediente, la cronología no repite su título (`variant="dossier"`).
- **Un clic en la cronología siempre hace algo.** Se abre la nota del hecho mejor ubicada (`mapLead`). Si ninguna tiene lugar, la ficha sale sin vuelo y con aviso.
