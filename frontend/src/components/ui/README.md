# Piezas de la «consola táctica» (`components/ui`)

Son las piezas visuales que comparten todas las pantallas del monitor. Los estilos están en `src/styles/hud.css` y tienen la forma de la «consola HUD» de Oráculo core (ADR-0108). La muestra de todas está en `http://localhost:8080/?diseno#/diseno`.

| Pieza            | Para qué                                                                       | Qué hace al pasar el mouse                                                     |
| ---------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| `HudPanel`       | Toda caja: tarjetas, paneles, fichas                                           | Con `interactive`, su borde se enciende                                        |
| `HudButton`      | Todas las acciones (`solid` la principal, `outline`, `ghost`, `danger`)        | Sube el tinte                                                                  |
| `HudChip`        | Estados y etiquetas (abierto, reservado, categoría)                            | Nada; con `live`, su punto late como radar                                     |
| `HudSegmented`   | Elegir una opción de pocas (Hoy · 7 días · 30 días)                            | Un tinte se desliza a la elegida                                               |
| `HudSelect`      | Todos los menús desplegables (en lugar de `<select>`)                          | La lista se despliega, la opción activa se ilumina y la elegida lleva palomita |
| `HudDatePicker`  | Fechas (en lugar de `<input type="date">`)                                     | Los días se iluminan; el elegido brilla y el mes cambia deslizándose           |
| `HudSwitch`      | Encender o apagar (fuentes)                                                    | La perilla viaja y se enciende en cian                                         |
| `HudDock`        | Menú de secciones: barra vertical a la izquierda (fila en celular)             | La sección elegida se ilumina con anillo y brillo cian                         |
| `HudTabs`        | Pestañas en fila (ya no se usan desde el 17/11/2026; quedan por si se regresa) | Una barra de luz sigue al mouse; los nombres se descifran                      |
| `CountUp`        | Cifras                                                                         | Corren hasta su valor al aparecer o cambiar                                    |
| `DecodeText`     | Títulos                                                                        | Se descifran letra por letra                                                   |
| `Sparkline`      | Tendencia junto a una cifra                                                    | Se dibuja de izquierda a derecha                                               |
| `SectionHeading` | Encabezado de cada pantalla                                                    | El título se descifra al aparecer                                              |
| `Heartbeat`      | Latido de un servicio (Estado del sistema)                                     | Un pulso de luz recorre la línea; plana y roja si falla                        |
| `Icon`           | Iconos de Material Icons, los de Oráculo (`<Icon name="close" />`)             | Nada; toma el color y el tamaño del texto de al lado                           |

**Reglas:**

- **Animar solo lo barato.** Se anima `transform`, `opacity` y sombras pequeñas. No se usan `backdrop-filter` ni filtros: el globo ya usa la tarjeta de video integrada.
- **Respetar a quien no quiere movimiento.** Con «reducir animaciones» en el sistema operativo, todo queda quieto.
- **Las clases sueltas también sirven:**
  - `.hud-table` para tablas (la de Oráculo core), y `.hud-row` y `.hud-trow` para filas de lista y de tabla;
  - `.hud-field` y `.hud-input` para campos, y `.hud-label` para sus etiquetas;
  - `.hud-seg` para el selector, y `.hud-subtab` para las subpestañas;
  - `.hud-section-head` y `.hud-section-title` para el encabezado de una sección;
  - `.hud-meter` y `.hud-progress` para barras de nivel y de avance;
  - `.hud-reveal` para la entrada escalonada;
  - `.hud-radar` para las corridas automáticas;
  - `.hud-empty` para el aviso «elige un elemento».
- **Iconos con `Icon`, no con caracteres** (× › ▾ ✓ ↗) **ni SVG sueltos.** Los nombres permitidos están en `IconName`; para agregar uno se busca en https://fonts.google.com/icons.
- **Con utilidades de Tailwind se ajusta cualquier pieza:** `hud.css` está en la capa `components`.
