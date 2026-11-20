/**
 * Configuración pública del servidor con TanStack Query.
 *
 * Cambia muy rara vez (solo al reiniciar el servidor): se pide una vez por
 * sesión. Un solo reintento: mientras se espera, la pantalla sin sesión no
 * muestra nada (decide entre el formulario y el aviso de Oráculo, ADR-0119),
 * y con los 3 reintentos de siempre un servidor caído la dejaba en blanco
 * varios segundos.
 */
import { useQuery } from '@tanstack/react-query';

import { getAppConfig } from '../services/appConfig';

export function useAppConfig() {
  return useQuery({
    queryKey: ['app-config'],
    queryFn: ({ signal }) => getAppConfig(signal),
    staleTime: Infinity,
    retry: 1,
  });
}
