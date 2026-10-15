/**
 * Servicio que consulta el estado del sistema (`GET /api/v1/health`).
 *
 * Lo usa el hook useHealth. Valida la forma de la respuesta antes de
 * entregarla, para que un cambio en la API se detecte aquí con un mensaje
 * claro y no como un error raro dentro de un componente.
 *
 * No hace: no decide cómo se muestra el estado ni cada cuánto se consulta.
 */
import { apiUrl } from '../config/api';

export type ComponentStatus = 'ok' | 'error';
export type SystemStatus = 'ok' | 'degraded';

export interface ComponentHealth {
  name: string;
  status: ComponentStatus;
  detail: string | null;
  latency_ms: number | null;
  info: Record<string, string>;
}

export interface SystemHealth {
  status: SystemStatus;
  components: ComponentHealth[];
}

/** Error al consultar el estado, con un mensaje en español para mostrar. */
export class HealthRequestError extends Error {
  override name = 'HealthRequestError';
}

// La API responde 503 cuando algún componente falla, pero el cuerpo sigue
// siendo un estado válido que hay que mostrar (especificación, sección 13).
const STATUSES_WITH_HEALTH_BODY = new Set([200, 503]);

function isComponentHealth(value: unknown): value is ComponentHealth {
  if (typeof value !== 'object' || value === null) return false;
  const c = value as Record<string, unknown>;
  return (
    typeof c.name === 'string' &&
    (c.status === 'ok' || c.status === 'error') &&
    (c.detail === null || typeof c.detail === 'string') &&
    (c.latency_ms === null || typeof c.latency_ms === 'number') &&
    typeof c.info === 'object' &&
    c.info !== null
  );
}

function isSystemHealth(value: unknown): value is SystemHealth {
  if (typeof value !== 'object' || value === null) return false;
  const h = value as Record<string, unknown>;
  return (
    (h.status === 'ok' || h.status === 'degraded') &&
    Array.isArray(h.components) &&
    h.components.every(isComponentHealth)
  );
}

/**
 * Consulta el estado de todos los componentes del sistema.
 *
 * @param signal Señal para cancelar la petición (la pasa TanStack Query).
 * @returns El estado del sistema, tanto si está sano como si está degradado.
 * @throws {HealthRequestError} Si la API no responde, responde con un código
 *   inesperado o con un cuerpo que no tiene la forma esperada.
 */
export async function fetchHealth(signal?: AbortSignal): Promise<SystemHealth> {
  let response: Response;
  try {
    response = await fetch(apiUrl('health'), { signal, headers: { Accept: 'application/json' } });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new HealthRequestError('No se pudo contactar a la API. ¿Está corriendo `make up`?');
  }

  if (!STATUSES_WITH_HEALTH_BODY.has(response.status)) {
    throw new HealthRequestError(
      `La API respondió con un código inesperado (${String(response.status)}).`,
    );
  }

  const body: unknown = await response.json().catch(() => null);
  if (!isSystemHealth(body)) {
    throw new HealthRequestError('La API respondió con un formato que no se reconoce.');
  }
  return body;
}
