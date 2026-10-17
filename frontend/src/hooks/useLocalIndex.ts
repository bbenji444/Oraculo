/**
 * Hooks del índice local con TanStack Query (CLAUDE.md §6.2).
 *
 * La búsqueda es una mutación: corre solo cuando la persona presiona
 * "Buscar". El resumen se refresca cada minuto mientras la pestaña está
 * abierta, para ver crecer el índice con la ingesta.
 */
import { useMutation, useQuery } from '@tanstack/react-query';

import { getIndexStats, searchLocalIndex } from '../services/localIndex';

// La ingesta corre cada 15 minutos; refrescar cada minuto basta para verla.
const STATS_REFRESH_MS = 60_000;

/** Resumen del índice local. */
export function useIndexStats() {
  return useQuery({
    queryKey: ['local-index', 'stats'],
    queryFn: ({ signal }) => getIndexStats(signal),
    refetchInterval: STATS_REFRESH_MS,
  });
}

/** Busca un concepto en el índice local. */
export function useLocalIndexSearch() {
  return useMutation({ mutationFn: searchLocalIndex });
}
