/**
 * Formato de fechas para la pestaña "Notas": siempre en hora de la Ciudad de
 * México (CLAUDE.md §6.3), aunque el navegador esté en otra zona.
 */
const MEXICO_CITY_FORMAT = new Intl.DateTimeFormat('es-MX', {
  timeZone: 'America/Mexico_City',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

/**
 * Fecha y hora en la Ciudad de México.
 *
 * @param iso Fecha ISO en UTC (como la manda la API).
 * @returns Por ejemplo "16/10/2026, 16:31".
 */
export function formatMexicoCity(iso: string): string {
  return MEXICO_CITY_FORMAT.format(new Date(iso));
}
