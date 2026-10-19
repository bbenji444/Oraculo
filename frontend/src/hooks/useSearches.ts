/**
 * Hooks de búsquedas y notas con TanStack Query (CLAUDE.md §6.2).
 *
 * - La estimación se pide sola al cambiar conceptos, región o fechas: no gasta.
 * - Lanzar es una mutación: solo al presionar "Buscar".
 * - El avance se consulta cada 2 s mientras la búsqueda corre y se detiene
 *   al terminar.
 * - Las notas se piden cuando la búsqueda terminó.
 */
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery } from '@tanstack/react-query';

import {
  estimateSearch,
  getArticle,
  getSearch,
  isFinished,
  listAllArticles,
  listSearches,
  type SearchInput,
  startSearch,
} from '../services/searches';
import { useDebouncedValue } from './useDebouncedValue';

// La pantalla consulta el avance cada 2 s (docs/api.md): se ve moverse sin
// cargar al servidor.
export const PROGRESS_POLL_MS = 2000;
// Espera tras el último cambio antes de re-estimar (al prender varios chips).
const ESTIMATE_DEBOUNCE_MS = 300;
// Una búsqueda terminada ya no cambia: sus notas se conservan.
const FINISHED_STALE_MS = Infinity;

/** Estimación de consultas, créditos y costo (o nada si falta algo). */
export function useEstimate(input: SearchInput | null) {
  const debounced = useDebouncedValue(input, ESTIMATE_DEBOUNCE_MS);
  return useQuery({
    queryKey: ['searches', 'estimate', debounced],
    queryFn: ({ signal }) => {
      // No pasa: la consulta está apagada mientras falte algo (enabled).
      if (debounced === null) throw new Error('Falta región o concepto.');
      return estimateSearch(debounced, signal);
    },
    enabled: debounced !== null,
    // Mientras llega la nueva, se sigue viendo la estimación anterior.
    placeholderData: keepPreviousData,
  });
}

/** Lanza una búsqueda; `onSuccess` recibe su id. */
export function useStartSearch(onStarted: (searchId: string) => void) {
  return useMutation({
    mutationFn: (input: SearchInput) => startSearch(input),
    onSuccess: onStarted,
  });
}

/** Estado y avance de una búsqueda; se repite cada 2 s hasta que termina. */
export function useSearch(searchId: string | null) {
  return useQuery({
    queryKey: ['searches', 'detail', searchId],
    queryFn: ({ signal }) => getSearch(searchId ?? '', signal),
    enabled: searchId !== null,
    refetchInterval: (query) =>
      query.state.data && isFinished(query.state.data.status) ? false : PROGRESS_POLL_MS,
  });
}

/** Todas las notas de una búsqueda terminada (relevantes y no relevantes). */
export function useSearchArticles(searchId: string | null, finished: boolean) {
  return useQuery({
    queryKey: ['searches', 'articles', searchId],
    queryFn: ({ signal }) => listAllArticles(searchId ?? '', { relevant: 'all' }, signal),
    enabled: searchId !== null && finished,
    staleTime: FINISHED_STALE_MS,
  });
}

/** Detalle de una nota. */
export function useArticle(articleId: number | null) {
  return useQuery({
    queryKey: ['articles', articleId],
    queryFn: ({ signal }) => getArticle(articleId ?? 0, signal),
    enabled: articleId !== null,
    staleTime: FINISHED_STALE_MS,
  });
}

/** Historial de búsquedas, por páginas. */
export function useSearchHistory() {
  return useInfiniteQuery({
    queryKey: ['searches', 'history'],
    queryFn: ({ pageParam, signal }) => listSearches(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}
