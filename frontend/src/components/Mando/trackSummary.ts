/**
 * La frase de «¿Qué rastrear?» que dice qué va a traer la búsqueda
 * (rediseño del 09/11/2026).
 *
 * No hace: no lee el store; recibe los nombres ya elegidos.
 */

/** «A», «A o B», «A, B o C». */
function either(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? '';
  return `${names.slice(0, -1).join(', ')} o ${names.at(-1) ?? ''}`;
}

/**
 * Lo que va a traer la búsqueda, en palabras.
 *
 * @param anchors Con quién (FGR, PDI…); vacío = con nadie.
 * @param crimes Delitos elegidos; vacío = todos.
 * @param independent Si se eligió «Con nadie en particular».
 * @example trackSummary(['FGR'], ['Homicidio'], false)
 *   // 'Notas de FGR que además hablan de Homicidio.'
 */
export function trackSummary(
  anchors: readonly string[],
  crimes: readonly string[],
  independent: boolean,
): string {
  if (anchors.length > 0) {
    return crimes.length === 0
      ? `Todo lo de ${either(anchors)}, de cualquier delito.`
      : `Notas de ${either(anchors)} que además hablan de ${either(crimes)}.`;
  }
  if (independent) {
    return crimes.length === 0
      ? 'Elige al menos un delito.'
      : `Todas las notas de ${either(crimes)}, aparezca o no alguien en particular.`;
  }
  return 'Elige con quién o un delito.';
}
