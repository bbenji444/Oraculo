/**
 * Cálculos del menú desplegable `HudSelect` (27/10/2026): moverse con el
 * teclado, buscar escribiendo y decidir si el menú abre hacia abajo o hacia
 * arriba.
 *
 * Funciones puras (sin DOM), para probarlas sin navegador.
 *
 * No hace: no dibuja ni escucha eventos.
 */

/** Alto máximo del menú abierto, en píxeles (unas 8 opciones). */
export const MENU_MAX_HEIGHT = 288;
/** Separación entre el campo y el menú, en píxeles. */
export const MENU_GAP = 6;
/** Margen con el borde de la ventana, en píxeles. */
const VIEWPORT_MARGIN = 12;
/** Alto mínimo del menú para que valga la pena abrir hacia un lado. */
const MIN_MENU_HEIGHT = 140;

/**
 * La opción a la que se llega con una flecha (o Inicio/Fin), sin dar la vuelta.
 *
 * @example moveIndex(0, -1, 5) // 0
 */
export function moveIndex(current: number, delta: number, count: number): number {
  if (count === 0) return -1;
  return Math.min(Math.max(current + delta, 0), count - 1);
}

/** Texto para comparar: minúsculas y sin acentos (la ñ se conserva). */
export function foldText(text: string): string {
  // Se parte en las ñ para que el quitar acentos no las vuelva n.
  return text
    .toLowerCase()
    .split('ñ')
    .map((part) => part.normalize('NFD').replace(/\p{M}/gu, ''))
    .join('ñ');
}

/**
 * La primera opción, después de `from`, cuyo texto empieza con lo escrito.
 * Si no hay después, se busca desde el principio.
 *
 * @example matchTypeahead(['Jalisco', 'Michoacán', 'México'], 'me', 0) // 2
 * @returns Su posición, o -1 si ninguna coincide.
 */
export function matchTypeahead(labels: readonly string[], query: string, from: number): number {
  const wanted = foldText(query);
  if (!wanted) return -1;
  const count = labels.length;
  for (let step = 1; step <= count; step++) {
    const index = (from + step) % count;
    const label = labels[index];
    if (label !== undefined && foldText(label).startsWith(wanted)) return index;
  }
  return -1;
}

export interface MenuPlacement {
  /** El menú abre hacia arriba del campo. */
  above: boolean;
  /** Distancia desde arriba de la ventana (si abre hacia abajo). */
  top: number;
  /** Distancia desde abajo de la ventana (si abre hacia arriba). */
  bottom: number;
  left: number;
  minWidth: number;
  maxHeight: number;
}

/**
 * Dónde se dibuja el menú: debajo del campo si cabe; si no, arriba, del lado
 * con más espacio. Nunca se sale de la ventana.
 *
 * @param anchor Rectángulo del campo en la ventana.
 * @param viewport Tamaño de la ventana.
 */
export function menuPlacement(
  anchor: Pick<DOMRect, 'top' | 'bottom' | 'left' | 'width'>,
  viewport: { width: number; height: number },
): MenuPlacement {
  const below = viewport.height - anchor.bottom - MENU_GAP - VIEWPORT_MARGIN;
  const above = anchor.top - MENU_GAP - VIEWPORT_MARGIN;
  const openAbove = below < MIN_MENU_HEIGHT && above > below;
  const room = openAbove ? above : below;
  const maxLeft = Math.max(VIEWPORT_MARGIN, viewport.width - anchor.width - VIEWPORT_MARGIN);
  return {
    above: openAbove,
    top: anchor.bottom + MENU_GAP,
    bottom: viewport.height - anchor.top + MENU_GAP,
    left: Math.min(Math.max(anchor.left, VIEWPORT_MARGIN), maxLeft),
    minWidth: anchor.width,
    maxHeight: Math.max(Math.min(MENU_MAX_HEIGHT, room), MIN_MENU_HEIGHT / 2),
  };
}
