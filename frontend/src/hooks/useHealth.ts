/**
 * Hook que mantiene actualizado el estado del sistema con TanStack Query.
 *
 * Consulta /health al montar el componente y luego cada cierto tiempo, para
 * que el semáforo refleje si un servicio se cae o se recupera.
 */
import { useQuery } from '@tanstack/react-query';

import { fetchHealth } from '../services/health';

// 10 s: suficiente para notar un cambio sin cargar la API en desarrollo.
const HEALTH_REFRESH_MS = 10_000;

/** Devuelve el estado de la consulta de salud (datos, error y si está cargando). */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => fetchHealth(signal),
    refetchInterval: HEALTH_REFRESH_MS,
    // Un fallo de /health ya es información: no tiene caso reintentar en silencio.
    retry: false,
  });
}
