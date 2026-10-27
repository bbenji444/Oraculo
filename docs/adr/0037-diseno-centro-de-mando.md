# ADR-0037: Diseño «Centro de mando» para la búsqueda (diseño 3)

- **Estado:** Propuesto (27/10/2026). Está detrás de `?mando` en la URL para compararlo con el diseño 2 («consola táctica»). Benji decide cuál se queda.
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
- Para verlo se abre `http://localhost:8080/?mando#/explorar`. Sin `?mando` se ve el diseño 2.
- **Riesgo:** en pantallas bajas (menos de ~650 px de alto), la consola y el expediente dejan poco lugar al globo. El zoom tiene un tope inferior (`GLOBE_FIT_MIN_ZOOM`) para que no se vuelva una canica.
- Si Benji elige este diseño, falta:
  - quitar la bandera `?mando`;
  - decidir qué pasa con la columna del diseño 2;
  - agregar una prueba de humo del flujo completo con este diseño.
