/**
 * Clases compartidas de los paneles translúcidos de Explorar (estilo de las
 * imágenes de referencia de Benji): el globo se ve detrás.
 */

/**
 * Panel de vidrio oscuro sobre el universo.
 *
 * En modo día (`data-earth="day"` en Explorar) el vidrio se oscurece: sobre el
 * mapa claro de calles, al 60 % quedaba gris y el texto secundario medía
 * 1.6 : 1 de contraste (prueba operativa del 20/10/2026; se pide 4.5 : 1). De
 * noche se queda translúcido, como en las imágenes de referencia.
 */
export const GLASS =
  'rounded-2xl border border-white/10 bg-slate-950/60 shadow-2xl shadow-black/50 backdrop-blur-md [[data-earth=day]_&]:bg-slate-950/85';

/** Título de panel. */
export const PANEL_TITLE = 'text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-200/80';

/** Botón secundario pequeño. */
export const SMALL_BUTTON =
  'rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-slate-200 transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-40';
