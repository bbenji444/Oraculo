/**
 * Qué dice el chip «Estado del sistema» (`StatusChip`, ADR-0108) según la
 * consulta de /health: el color del piloto y la frase.
 *
 * Va aparte del componente para poder probarlo sin dibujar nada.
 *
 * No hace: no consulta /health (eso es `useHealth`).
 */
import type { SystemHealth } from '../../services/health';

export type StatusChipState = 'checking' | 'ok' | 'degraded' | 'down';

/**
 * Qué dice el chip según la consulta de salud.
 *
 * @param query Datos y error, como los da `useHealth`.
 * @returns El estado (para el color del piloto) y la frase.
 */
export function statusChipOf(query: { data?: SystemHealth; error: Error | null }): {
  state: StatusChipState;
  label: string;
} {
  // Primero el error: si la última consulta falló, los datos que quedan son
  // de antes y ya no dicen cómo está ahora.
  if (query.error) return { state: 'down', label: 'Estado del sistema: sin conexión' };
  if (query.data?.status === 'ok') return { state: 'ok', label: 'Estado del sistema: en línea' };
  if (query.data?.status === 'degraded') {
    return { state: 'degraded', label: 'Estado del sistema: con fallas' };
  }
  return { state: 'checking', label: 'Estado del sistema: revisando…' };
}
