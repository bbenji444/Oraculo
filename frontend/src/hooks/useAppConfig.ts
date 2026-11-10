/**
 * Configuración pública del servidor con TanStack Query.
 *
 * Cambia muy rara vez (solo al reiniciar el servidor): se pide una vez por
 * sesión.
 */
import { useQuery } from '@tanstack/react-query';

import { getAppConfig } from '../services/appConfig';

export function useAppConfig() {
  return useQuery({
    queryKey: ['app-config'],
    queryFn: ({ signal }) => getAppConfig(signal),
    staleTime: Infinity,
  });
}
