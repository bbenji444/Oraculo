# ADR-0116: Esfera de búsqueda en «Todo el mundo»

- **Estado:** propuesto (18/11/2026), en espera de que Benji lo vea en pantalla.
- **Fase:** F12.

## Contexto

Benji (18/11/2026) pidió que la búsqueda se sienta «casi tan natural como buscar en Google». Para «Todo el mundo» (región `WLD`, ADR-0112) pidió, en lugar de la cúpula, «una esfera tenue que envuelva toda la Tierra con la misma textura de la cúpula y una animación chida solo mientras se busca».

La cúpula (`map/radar/dome.ts`, 11/11/2026) se pensó para una zona. Con «Mundo» se veía mal por tres razones:

1. **Forma.** `domeShape` toma el punto medio del rectángulo de la región. Con el `focus_bbox` de «Mundo» (`[-180, -58, 180, 75]`) el centro cae en `[0, 8.5]`, en Ghana. El radio pedido sería 21,799 km, pero el tope lo deja en 1,600 km. Resultado: una cúpula sobre África occidental que no representa «todo el mundo». Lo documenta una prueba en `dome.test.ts`.
2. **Cámara.** Al elegir «Mundo», el globo se aleja a su vista general y gira (`showOverview`). La cúpula, además, volaba a Ghana con 60° de inclinación. Como el giro seguía encendido, el globo terminaba girando inclinado y la cúpula se iba detrás del planeta.
3. **Letreros.** Decían «8.50° N · 0.00° E» y se pegaban a las esquinas del rectángulo. En el antimeridiano esas esquinas coinciden, así que la caja salía de ancho cero y detrás del globo.

## Decisión

1. **«Todo el mundo» se reconoce al instante por `search.region_code === 'WLD'`**, sin esperar el detalle de la región. Las demás regiones conservan la cúpula sin ningún cambio.
2. **Una capa propia de MapLibre en WebGL 2** (`map/radar/shell.ts`), como la cúpula:
   - es una esfera a 6 % del radio terrestre sobre el suelo (unos 380 km), que deja un halo de ~20 px alrededor del globo a zoom 2;
   - usa el mismo material de la cúpula: cian con mezcla aditiva, 12 meridianos y 6 paralelos, el borde encendido y el haz del radar;
   - su brillo es 0.55 del de la cúpula y baja a 60 % en modo día, para no lavar la textura clara;
   - cada vértice va a la esfera directo desde su longitud y latitud, sin pasar por Mercator (que no llega a los polos);
   - lo que queda detrás de la Tierra se recorta con el plano de horizonte de MapLibre (`globeComputeClippingZ`);
   - el brillo del borde sale del ángulo de vista. La posición de la cámara se calcula del plano de recorte, `[n, −1/D]`. Es una convención interna de maplibre-gl 6.14.0, marcada «VERIFICAR al actualizar»;
   - de cerca (cámara a menos de 1.6 radios del centro, más o menos zoom 5) la esfera se apaga, para que la cámara no quede dentro y tiña toda la pantalla. Solo se dibuja con el globo, no con el mapa plano.
3. **Animación en tres tiempos:**
   - **Aparición (1.4 s):** la esfera sube del suelo y un frente de luz la recorre de sur a norte descubriendo la rejilla.
   - **Mientras se busca:**
     - un meridiano de luz le da la vuelta al planeta (el haz, a la misma velocidad que el de la cúpula);
     - un anillo de latitud va y viene de polo a polo;
     - el borde «respira»;
     - cada nota encendida enciende un ping (un anillo que se abre, con un destello al nacer).
   - **Al terminar (0.9 s):** destello, la esfera se expande a 1.5 veces su altura y se desvanece. Luego se quita la capa y queda el letrero «BARRIDO COMPLETO», que ya existía y aparece al mismo tiempo, con su propio desvanecido.
4. **Los pings nacen en la cara visible**, a menos de 50° del centro de la vista en el momento en que llega la nota. Siguen una espiral de girasol con lugares fijos: no brincan al llegar más y quedan a 15.7° entre sí como mínimo (medido). Son decorativos: van sobre el vidrio y no bajan columnas al suelo, para que no parezcan ubicaciones de notas.
5. **La cámara no se toca:** nada de vuelo, nada de inclinación a 60° y nada de enderezar al final. El globo sigue en su vista general y gira dentro de la esfera.
6. **Letreros:**
   - sobre el borde de arriba de la esfera, «Barrido en curso · Todo el mundo» con «Cobertura global · noticias en español» en lugar de coordenadas (se oculta en celular, como las coordenadas);
   - debajo, la etapa y las notas detectadas;
   - nunca suben hasta el encabezado.
   - Se colocan con la silueta del globo en pantalla (`globeOutline`, que pasó de ExploreGlobe a `map/framing.ts` como función pura).
7. **Respaldos:**
   - si la tarjeta de video no puede con los shaders (al ponerla o ya puesta, cuando su `render` avisa con `onFailure`), se muestra el radar plano CSS centrado en la silueta del globo y del tamaño de la esfera;
   - si el estilo del mapa está a medio cargar, se muestra el radar plano y la esfera se pone en cuanto termina de cargar (`style.load`);
   - sobre el globo, el radar plano no lleva sus letreros colgados arriba y abajo, que quedaban detrás del encabezado y de la consola (revisión del 18/11/2026). Lleva los mismos letreros que la esfera, en el mismo bloque y con el mismo tope bajo el encabezado. Sin mapa todavía, el radar plano va al centro de la parte libre, del tamaño de siempre y con sus letreros.
8. **«Menos movimiento»:** la esfera queda quieta, aparece y se quita al instante y nunca pide cuadros de más (medido: 0 pedidos extra de redibujo).
9. **Refactor previo, sin cambio de comportamiento:** la plomería WebGL que compartían en espíritu la cúpula y la esfera pasó a `map/radar/gl.ts`: compilar, mallas, atributos, uniforms de proyección y la función `line()` de la rejilla. Las ubicaciones de los uniforms ahora se guardan en caché en lugar de pedirse en cada cuadro.
10. **Números de los shaders con nombre** (revisión del 18/11/2026). Los pesos y ritmos del shader de la esfera son constantes de TypeScript con su origen («ajustado a ojo con capturas»), y se escriben en el GLSL con `glslFloat()`. La cúpula usa también `glslFloat()` para lo que comparte con la esfera (velocidad y estela del haz) y las dos toman la rejilla de `gl.ts` (`GRID_MERIDIANS`, `GRID_PARALLELS` y sus grosores). El texto del shader de la cúpula salió idéntico, comparado antes y después. El de la esfera da el mismo resultado: solo cambiaron saltos de línea, `1e-4` se escribe `0.0001` y el factor `(0.25 + 0.75 · borde)`, que se repetía, se calcula una vez. `shaders.test.ts` revisa que la cúpula y la esfera giren igual, que usen la misma rejilla y que ningún número quede como entero suelto, que GLSL no compila donde espera un `float`.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Agrandar la cúpula (quitar el tope de radio) | Una media esfera de 20,000 km de radio sobre Ghana tapa medio planeta y sigue sin envolverlo. Tampoco arregla el choque con el giro. |
| three.js (ya es dependencia, para el fondo de universo) | Habría que sincronizar su cámara con la de MapLibre cuadro a cuadro y recortar contra el globo a mano. La capa propia de MapLibre trae la proyección y el recorte. |
| Overlay CSS o SVG sobre la silueta | Una rejilla de meridianos en CSS no gira con el globo ni respeta la inclinación del eje (`GLOBE_BEARING`). Se usa solo como respaldo sin WebGL. |
| Pings en una esfera de Fibonacci fija (propuesta inicial) | La mitad nacería detrás del planeta y no se vería encender la nota. Además, con la razón áurea en el radio había pares a 2.7° y sus discos se encimaban. |
| Volar o alejar la cámara al empezar | Benji pidió que el globo siga girando. Cualquier vuelo o inclinación vuelve a chocar con el giro (ver Contexto, punto 2). |

## Consecuencias

- En «Todo el mundo» el analista ve que se busca en el planeta entero, sin que la cámara se mueva a un lugar que no significa nada.
- Rendimiento, medido el 18/11/2026 en Intel UHD Graphics (video integrado, D3D11) con el lienzo a 1600 × 1000:
  - `map.redraw()` más `gl.finish()`, 400 cuadros con la esfera y 18 pings contra 400 sin ella: mediana de 2.5 ms en ambos casos (60 fps son 16.7 ms por cuadro);
  - la malla tiene ~4,700 vértices, más ~300 por ping;
  - en «Mundo» el globo ya redibuja cada cuadro por el giro, así que la esfera casi no suma.
- La capa depende de dos convenciones internas de maplibre-gl 6.14.0, documentadas en el código y en `shell.test.ts`: la esfera unitaria con `y` al norte y la longitud 0 en `+z`, y el plano de recorte `[n, −1/D]`. Hay que revisarlas al actualizar maplibre-gl.
- Si el estilo se recarga por completo a media búsqueda (no un cambio con `diff`), MapLibre quita las capas propias y la esfera no vuelve hasta la siguiente búsqueda. Con la cúpula pasa lo mismo. El cambio día/noche usa `diff` y se comprobó que la esfera sigue.
- Los pings no son lugares: son un pulso por nota. Las notas se ven en su lugar real al terminar la búsqueda.
