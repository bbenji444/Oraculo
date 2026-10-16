/**
 * Hooks de datos de regiones con TanStack Query (CLAUDE.md §6.2).
 *
 * El catálogo cambia solo cuando se recarga INEGI, así que los resultados se
 * conservan varios minutos sin volver a pedirlos.
 */
import { useQuery } from '@tanstack/react-query';

import { getRegion, searchRegions } from '../services/regions';
import { useDebouncedValue } from './useDebouncedValue';

// Espera entre teclas antes de buscar: se siente inmediato y evita una
// petición por letra.
const SEARCH_DEBOUNCE_MS = 250;
// La API exige al menos 2 letras (app/application/use_cases/regions.py).
const MIN_SEARCH_LENGTH = 2;
const CATALOG_STALE_MS = 5 * 60_000;

/** Busca regiones mientras la persona escribe. */
export function useRegionSearch(query: string) {
  const debounced = useDebouncedValue(query.trim(), SEARCH_DEBOUNCE_MS);
  const enabled = debounced.length >= MIN_SEARCH_LENGTH;
  return {
    ...useQuery({
      queryKey: ['regions', 'search', debounced],
      queryFn: ({ signal }) => searchRegions(debounced, signal),
      enabled,
      staleTime: CATALOG_STALE_MS,
    }),
    enabled,
  };
}

/** Detalle de la región seleccionada (o nada si no hay selección). */
export function useRegionDetail(id: number | null) {
  return useQuery({
    queryKey: ['regions', 'detail', id],
    queryFn: ({ signal }) => getRegion(id ?? 0, signal),
    enabled: id !== null,
    staleTime: CATALOG_STALE_MS,
  });
}
