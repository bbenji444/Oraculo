# Piezas de la «consola táctica» (`components/ui`)

Son las piezas visuales que comparten todas las pantallas del monitor. Los estilos están en `src/styles/hud.css` y la luz que sigue al mouse en `src/ui/spotlight.ts`. La muestra de todas está en `http://localhost:8080/?diseno#/diseno`.

| Pieza            | Para qué                                                                | Qué hace al pasar el mouse                                                    |
| ---------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `HudPanel`       | Toda caja: tarjetas, paneles, fichas                                    | Halo y borde de luz donde está el cursor; con `interactive`, se eleva         |
| `HudButton`      | Todas las acciones (`solid` la principal, `outline`, `ghost`, `danger`) | Brilla, una franja de luz lo cruza, el texto se abre; al hacer clic, una onda |
| `HudChip`        | Estados y etiquetas (abierto, reservado, categoría)                     | Se enciende; con `live`, su punto late como radar                             |
| `HudSegmented`   | Elegir una opción de pocas (Hoy · 7 días · 30 días)                     | Una pastilla de luz se desliza a la elegida                                   |
| `HudSwitch`      | Encender o apagar (fuentes)                                             | El punto viaja y se enciende                                                  |
| `HudTabs`        | Pestañas del encabezado                                                 | Una barra de luz sigue al mouse; los nombres se descifran                     |
| `CountUp`        | Cifras                                                                  | Corren hasta su valor al aparecer o cambiar                                   |
| `DecodeText`     | Títulos                                                                 | Se descifran letra por letra                                                  |
| `Sparkline`      | Tendencia junto a una cifra                                             | Se dibuja de izquierda a derecha                                              |
| `SectionHeading` | Encabezado de cada pantalla                                             | Línea que se dibuja y título que se descifra                                  |

**Reglas:**

- **Animar solo lo barato.** Se anima `transform`, `opacity` y sombras pequeñas. No se usan `backdrop-filter` ni filtros: el globo ya usa la tarjeta de video integrada.
- **Respetar a quien no quiere movimiento.** Con «reducir animaciones» en el sistema operativo, todo queda quieto.
- **Las clases sueltas también sirven** (`.hud-row`, `.hud-field`, `.hud-meter`, `.hud-reveal`, `.hud-radar`), para listas, campos, barras de nivel, entradas escalonadas y corridas automáticas.
