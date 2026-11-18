# ADR-0108: Homologación visual con Oráculo core (nivel medio)

- **Estado:** aceptado (17/11/2026). Benji aprobó el plan del nivel medio con estas recomendaciones:
  - «ORÁCULO» + «NOTICIAS» en el encabezado;
  - constelación fuera de Explorar;
  - Material Icons.

  Puso una condición: **se conservan todas las secciones actuales**.

- **Fase:** F12.

## Contexto

Oráculo core es el sistema principal. Corre en el servidor OraculoApp, en Django, con plantillas y CSS propios. Su Hub ya abre el monitor como el módulo «Noticias Intelligence». Al dar clic se nota el brinco: el monitor se parece, pero no es igual.

Oráculo documenta su diseño en `docs/design_system.md`, la «consola HUD»:

- **Colores:** el color es estado.
  - cian `#00d2ff` = sistema;
  - verde `#00ff9d` = con datos;
  - ámbar `#ffb020` = aviso;
  - rojo `#ff3333` = error.
- **Letras:** Orbitron en rótulos, botones y cifras; Roboto en el texto.
- **Formas:** esquinas de 4px, con corchetes en dos esquinas de cada tarjeta.
- **Marco fijo:** encabezado con logo y chip de usuario, y un chip «Estado del sistema» abajo.
- **Fondo:** cuadrícula tenue con una constelación.

El 17/11/2026 se leyó su CSS exacto del servidor, en solo lectura, y se midió en vivo con la sesión de Benji. Las letras ya se cambiaron en el commit 0ab0735 (ADR-0037).

Benji eligió el nivel medio de tres posibles. El monitor debe parecer otra pantalla de Oráculo sin mover dónde están las cosas. Las pestañas (Explorar, Casos, Conceptos, Historial, Envíos, Estado del sistema y Accesos) se quedan.

## Decisión

**El cambio se hace desde el centro, no componente por componente.**

- Se redefinen las escalas de Tailwind en `@theme`:
  - colores de estado: `emerald`, `amber` y `rose`, con el tono 400 de Oráculo;
  - radios: `--radius-md` a `--radius-3xl` a 4px.
- Las clases de `hud.css` y `mando.css` toman la forma de las piezas de Oráculo y **conservan su nombre**. Así los componentes de `src/components/ui/` y los cientos de usos en los `.tsx` cambian sin tocarlos.

Cada paso va en su propio commit, para revertirlo solo:

1. Colores de estado y esquinas.
2. Paneles con los dos corchetes de `.jarvis-card` y la superficie de consola, sin la luz que sigue al mouse.
3. Botones, etiquetas, campos, interruptores, pestañas y títulos, como `.jarvis-btn`, `.jarvis-badge`, `.jarvis-input`, `.jarvis-switch` y `.jarvis-page-title`.
4. Ventanas, como `.jarvis-modal-card`, y tablas, como `.jarvis-data-table`.
5. Encabezado, pie y fondo:
   - logo de Oráculo + «ORÁCULO · NOTICIAS». El logo regresa al Hub (reemplaza el botón «← Oráculo»);
   - chip de usuario y chip de estado. El de estado va abajo al centro, menos en Explorar, donde esa franja es de «Consulta activa»;
   - constelación fuera de Explorar. El universo 3D ya no se monta en las demás pestañas.

   Para que las 7 pestañas quepan en una fila con la sesión completa: bajo 1536 px se juntan, bajo 1440 px se quita el texto «ORÁCULO» y bajo 1280 px se achican y se quita el nombre de la persona. Medido de 1024 a 1534 px. Bajo 1024 px se deslizan a lo ancho, como ya pasaba en celular.

6. Iconos: Material Icons autoalojados.
7. **Menú a la izquierda (17/11/2026, después de publicar los pasos 1 a 6).** El jefe de Benji pidió el dock vertical de Oráculo, que aquí estaba en «Alternativas» como parte del nivel completo. Las 7 secciones pasan a `HudDock`: barra vertical de 72 px a la izquierda, centrada bajo el encabezado, con icono y nombre corto debajo (Benji eligió que llevara nombre, no solo icono, para analistas sin capacitación). `--dock-w` reserva su espacio: las pantallas empiezan a la derecha y en Explorar se recorren los paneles; el globo sigue a pantalla completa. En celular se queda en el encabezado como fila deslizable: abajo chocaría con la consola de Explorar. Con el encabezado libre, «ORÁCULO» y el nombre de la persona se ven siempre (se quitaron los cortes por ancho del paso 5).

**De Oráculo no se copia:**

| Lo que hace Oráculo                                                 | Por qué no                                               |
| ------------------------------------------------------------------- | -------------------------------------------------------- |
| `backdrop-filter`                                                   | El monitor lo evita para no frenar el globo (`hud.css`). |
| Botones sin foco visible                                            | Se conserva el foco para quien usa teclado.              |
| Celdas de tabla sin relleno                                         | Es un descuido de su CSS.                                |
| Constelación que anima aunque el sistema pida «reducir animaciones» | El monitor siempre respeta esa preferencia.              |

## Alternativas consideradas

| Alternativa                                                                                | Por qué no                                                                                                                                                                                                        |
| ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nivel ligero: solo letras, esquinas y botones                                              | El encabezado y el fondo seguirían delatando que es otro sistema.                                                                                                                                                 |
| Nivel completo: dock vertical en lugar de pestañas, animaciones de tubo y PDF tipo dossier | Cambia la costumbre de los analistas. Además, el lado izquierdo de Explorar ya tiene paneles sobre el globo. Queda para después. El dock se hizo después (paso 7); las animaciones de tubo y el PDF siguen fuera. |
| Copiar el CSS de Oráculo tal cual                                                          | Su stack es Django con CSS suelto y el del monitor es React con Tailwind. Se copia el molde, no la prenda.                                                                                                        |
| Componente por componente                                                                  | Habría que tocar decenas de `.tsx` y quedarían piezas sin homologar.                                                                                                                                              |

## Consecuencias

- Al pasar del Hub de Oráculo al monitor se siente el mismo sistema.
- Se pierden señas propias del monitor:
  - el letrero de neón (02/11);
  - las esquinas redondeadas con cuatro marcas;
  - la luz que sigue al mouse;
  - las estrellas 3D fuera de Explorar.
- Si Oráculo cambia su guía, hay que repetir la homologación a mano: no comparten archivos.
- Se homologa el modo oscuro, el que se usa por defecto. Oráculo no tiene modo claro.
