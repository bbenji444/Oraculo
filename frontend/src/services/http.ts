/**
 * Cliente HTTP compartido por los servicios de src/services/.
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2). Aquí se
 * centraliza cómo se habla con la API: JSON de ida y vuelta, y traducción
 * del formato uniforme de error (`{"error": {"code", "message", "details"}}`)
 * a un `ApiError` con el mensaje en español tal cual.
 */

/** Error de la API con su mensaje en español, su código estable y sus detalles. */
export class ApiError extends Error {
  override name = 'ApiError';
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(message: string, code: string, details: Record<string, unknown> = {}) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

/** Error cuando la respuesta no tiene la forma esperada. */
export function badFormat(): ApiError {
  return new ApiError('La API respondió con un formato que no se reconoce.', 'bad_format');
}

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE';

interface RequestOptions {
  method?: Method;
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * Hace una petición y devuelve el cuerpo JSON (o `null` en un 204).
 *
 * @param url URL relativa de la API (ver `apiUrl`).
 * @param options Método, cuerpo (se envía como JSON) y señal para cancelar.
 * @returns El cuerpo de la respuesta, sin validar su forma.
 * @throws {ApiError} `network_error` si no hay conexión, o el error de la API.
 */
export async function requestJson(url: string, options: RequestOptions = {}): Promise<unknown> {
  const { method = 'GET', body, signal } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      signal,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('No se pudo contactar a la API.', 'network_error');
  }
  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw errorFrom(response.status, payload);
  return payload;
}

/** Traduce el formato uniforme de error de la API a un `ApiError`. */
function errorFrom(status: number, payload: unknown): ApiError {
  const apiError = (
    payload as { error?: { message?: unknown; code?: unknown; details?: unknown } } | null
  )?.error;
  const details =
    typeof apiError?.details === 'object' && apiError.details !== null
      ? (apiError.details as Record<string, unknown>)
      : {};
  return new ApiError(
    typeof apiError?.message === 'string'
      ? apiError.message
      : `La API respondió con error (${String(status)}).`,
    typeof apiError?.code === 'string' ? apiError.code : 'http_error',
    details,
  );
}

/** Un archivo que entregó la API (reporte o datos). */
export interface ApiFile {
  blob: Blob;
  /** Nombre que sugiere la API en `Content-Disposition`, si lo manda. */
  filename: string | null;
}

/**
 * Pide un archivo a la API (PDF, HTML, CSV o GeoJSON).
 *
 * @param url URL relativa de la API (ver `apiUrl`).
 * @param method `GET` o `POST` (el reporte se genera con POST, §13).
 * @returns El contenido y el nombre sugerido.
 * @throws {ApiError} `network_error` si no hay conexión, o el error de la API
 *   (por ejemplo `search_not_finished` si la búsqueda todavía corre).
 */
export async function requestFile(url: string, method: 'GET' | 'POST' = 'GET'): Promise<ApiFile> {
  let response: Response;
  try {
    response = await fetch(url, { method });
  } catch {
    throw new ApiError('No se pudo contactar a la API.', 'network_error');
  }
  if (!response.ok) throw errorFrom(response.status, await response.json().catch(() => null));
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? null;
  return { blob: await response.blob(), filename };
}
