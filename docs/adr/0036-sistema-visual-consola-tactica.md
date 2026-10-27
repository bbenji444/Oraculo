# ADR-0036: Sistema visual «consola táctica» para todo el monitor

- **Estado:** Propuesto (27/10/2026). Falta que Benji apruebe la muestra (`?diseno#/diseno`) antes de aplicarlo a todas las pantallas.
- **Fecha:** 27 de octubre de 2026
- **Fase:** F12
- **Decide:** Benji (27/10/2026: su jefe vio el monitor «como un Tsuru, no un Tesla»: genérico, sin animación. «Algo que le interesa mucho son los botones, el texto, que cuando pasas el mouse encima de un componente haga algo… enfócate 100 % en un diseño súper futurista y pro»)

## Contexto

La interfaz usa los colores y las fuentes de OSINT Oráculo (cian `#00d2ff` sobre negro; Orbitron y Roboto). Pero sus piezas son las de serie de Tailwind:

- cajas grises planas;
- botones de un solo color;
- listas sin respuesta al mouse.

Todas las pantallas se ven iguales y nada reacciona.

Una restricción técnica: la computadora de Benji tiene una tarjeta Intel integrada. El globo 3D ya la exige, y se reinició varias veces el 26/10/2026.

## Decisión

1. **Un lenguaje visual común:** una «consola táctica holográfica», con piezas en `src/components/ui` y estilos en `src/styles/hud.css`:
   - paneles con esquinas de mira y un borde de luz que sigue al mouse;
   - botones con destello, onda al hacer clic y texto que se abre;
   - insignias con pulso de radar;
   - pestañas con una barra de luz deslizante y nombres que se descifran;
   - cifras que corren hasta su valor, con mini gráficas que se dibujan;
   - campos con haz de enfoque;
   - entradas escalonadas.
2. **Animar solo lo barato.** `transform`, `opacity` y sombras pequeñas; nada de `backdrop-filter` ni filtros. La luz del mouse usa un solo oyente para toda la página, que mueve dos variables CSS una vez por cuadro.
3. **Respetar «reducir animaciones».** Con esa opción del sistema operativo, todo queda quieto.
4. **Mostrar antes de aplicar.** Primero se arma una muestra con datos reales, para que Benji la apruebe. Las pestañas del encabezado ya usan la pieza nueva.

## Alternativas consideradas

- **Una librería de componentes** (shadcn, MUI): traen su propio estilo genérico; justo lo que se quiere dejar atrás.
- **Librerías de animación** (Framer Motion, GSAP): agregan peso y una dependencia nueva. Lo pedido se logra con CSS y unas pocas líneas.
- **Vidrio esmerilado** (`backdrop-filter: blur`): se ve bien, pero sobre el globo 3D costaría cuadros en la tarjeta integrada.

## Consecuencias

- Todas las pantallas se reescriben con las mismas piezas, así que el estilo queda en un solo lugar.
- Pendiente tras la aprobación: aplicarlo a Explorar (panel de búsqueda, ficha, cronología, controles), Casos, Conceptos, Historial y Estado del sistema. También corregir de paso la tarjeta de Historial que se desarma en pantallas angostas.
