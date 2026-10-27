/**
 * Clases compartidas de los paneles de Explorar, con el diseño «consola
 * táctica» (ADR-0036, styles/hud.css): el globo se ve detrás.
 */

/**
 * Panel de la consola sobre el universo: vidrio oscuro con esquinas de mira y
 * un halo que sigue al mouse.
 *
 * Sin `backdrop-blur` (27/10/2026): desenfocar lo que hay detrás obligaba a la
 * tarjeta Intel a volver a dibujar el globo cada cuadro, y se reiniciaba.
 *
 * En modo día (`data-earth="day"` en Explorar) el vidrio se oscurece: sobre el
 * mapa claro de calles, al 60 % quedaba gris y el texto secundario medía
 * 1.6 : 1 de contraste (prueba operativa del 20/10/2026; se pide 4.5 : 1).
 */
export const GLASS = 'hud-panel hud-spot [[data-earth=day]_&]:bg-slate-950/90';

/** Título de panel. */
export const PANEL_TITLE =
  'font-display text-[10.5px] font-semibold uppercase tracking-[0.24em] text-sky-300 [text-shadow:0_0_10px_rgb(0_210_255/0.45)]';

/** Botón secundario pequeño (con destello y onda, `.hud-btn`). */
export const SMALL_BUTTON = 'hud-btn hud-btn--sm';
