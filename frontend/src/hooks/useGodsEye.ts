/**
 * Si God's Eye View está respondiendo, con TanStack Query (27/10/2026).
 *
 * Mientras no responde se vuelve a revisar cada pocos segundos, para que la
 * pestaña lo muestre en cuanto arranque (`make up` tarda en preparar Cesium).
 */
import { useQuery } from '@tanstack/react-query';

import { isGodsEyeUp } from '../services/godsEye';

// Cada 5 s mientras está apagado: arranca en 10 a 60 s y no cuesta nada revisar.
const RETRY_WHILE_DOWN_MS = 5_000;

/** Estado de la revisión: `data` es `true` si el módulo contestó. */
export function useGodsEye(url: string) {
  return useQuery({
    queryKey: ['gods-eye', url],
    queryFn: ({ signal }) => isGodsEyeUp(url, signal),
    refetchInterval: (query) => (query.state.data === true ? false : RETRY_WHILE_DOWN_MS),
    retry: false,
  });
}
