/**
 * Cuántos workers de MapLibre usar (los hilos que decodifican teselas).
 *
 * MapLibre 6 usa uno solo fuera de Safari: las teselas de calles se
 * decodificaban de una en una y el mapa «cargaba poco a poco» al llegar a una
 * nota (Benji, 27/10/2026). `setupMapLibre` aplica este número.
 *
 * No hace: no toca MapLibre (función pura, para probarla).
 */

// Tope de workers: cada uno guarda su propia copia del estilo y de las teselas
// en curso (memoria), y con más ya casi no se gana.
export const MAX_MAP_WORKERS = 4;

/**
 * La mitad de los procesadores, entre 1 y MAX_MAP_WORKERS: la otra mitad
 * queda libre para la página y el globo.
 *
 * @param hardwareConcurrency `navigator.hardwareConcurrency` (0 si no se sabe).
 * @returns El número de workers.
 *
 * @example
 *   mapWorkerCount(16) // 4 en la computadora de Benji
 */
export function mapWorkerCount(hardwareConcurrency: number): number {
  const half = Math.floor((hardwareConcurrency || 2) / 2);
  return Math.min(MAX_MAP_WORKERS, Math.max(1, half));
}
