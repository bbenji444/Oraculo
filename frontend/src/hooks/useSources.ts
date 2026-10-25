/**
 * Hook de las fuentes de la búsqueda manual (switches, F12.2) con TanStack Query.
 *
 * Las fuentes casi no cambian mientras la página está abierta (dependen de la
 * configuración del servidor), así que se piden una vez y se reutilizan.
 */
import { useQuery } from '@tanstack/react-query';

import { fetchSources } from '../services/sources';

// 5 min: si alguien configura una llave en el servidor, la página la ve pronto
// sin volver a pedir las fuentes en cada render.
const SOURCES_STALE_MS = 5 * 60 * 1000;

/** Las fuentes de `/sources`. */
export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: ({ signal }) => fetchSources(signal),
    staleTime: SOURCES_STALE_MS,
  });
}
