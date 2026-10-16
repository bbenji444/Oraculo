/**
 * Servicio de regiones: búsqueda y detalle (`/api/v1/regions`).
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2). Si la
 * API responde con su formato uniforme de error (`{"error": {...}}`), el
 * mensaje en español se entrega tal cual en un `ApiError`.
 */
import { apiUrl } from '../config/api';
import type { RegionLevel } from '../map/style';

export interface Region {
  id: number;
  level: RegionLevel;
  code: string;
  name: string;
  display_name: string;
  display_prefix: string;
  country_code: string;
  parent_id: number | null;
  point: { lon: number; lat: number };
  /** [oeste, sur, este, norte] */
  bbox: [number, number, number, number];
  has_polygon: boolean;
  aliases: string[];
}

export interface RegionRef {
  id: number;
  level: RegionLevel;
  code: string;
  name: string;
}

export interface RegionDetail extends Region {
  ancestors: RegionRef[];
  breadcrumb: string;
}

/** Error de la API con su mensaje en español y su código estable. */
export class ApiError extends Error {
  override name = 'ApiError';
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.code = code;
  }
}

const LEVELS = new Set(['country', 'state', 'municipality', 'locality']);

function isRegion(value: unknown): value is Region {
  if (typeof value !== 'object' || value === null) return false;
  const r = value as Record<string, unknown>;
  return (
    typeof r.id === 'number' &&
    typeof r.level === 'string' &&
    LEVELS.has(r.level) &&
    typeof r.code === 'string' &&
    typeof r.display_name === 'string' &&
    Array.isArray(r.bbox) &&
    r.bbox.length === 4
  );
}

async function getJson(url: string, signal?: AbortSignal): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('No se pudo contactar a la API.', 'network_error');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const apiError = (body as { error?: { message?: unknown; code?: unknown } } | null)?.error;
    throw new ApiError(
      typeof apiError?.message === 'string'
        ? apiError.message
        : `La API respondió con error (${String(response.status)}).`,
      typeof apiError?.code === 'string' ? apiError.code : 'http_error',
    );
  }
  return body;
}

/**
 * Busca regiones por nombre o alias ("izta", "cdmx").
 *
 * @param query Texto escrito por la persona (mínimo 2 letras).
 * @param signal Señal para cancelar (la pasa TanStack Query).
 * @returns Las regiones encontradas, de la más a la menos relevante.
 * @throws {ApiError} Con el mensaje de la API si la búsqueda no es válida.
 */
export async function searchRegions(query: string, signal?: AbortSignal): Promise<Region[]> {
  const url = `${apiUrl('regions/search')}?${new URLSearchParams({ q: query }).toString()}`;
  const body = (await getJson(url, signal)) as { items?: unknown } | null;
  if (!Array.isArray(body?.items) || !body.items.every(isRegion)) {
    throw new ApiError('La API respondió con un formato que no se reconoce.', 'bad_format');
  }
  return body.items;
}

/**
 * Detalle de una región con sus ancestros (migas de pan).
 *
 * @param id Id de la región.
 * @param signal Señal para cancelar.
 * @returns La región con `ancestors` y `breadcrumb`.
 * @throws {ApiError} Si no existe (`region_not_found`) o la API falla.
 */
export async function getRegion(id: number, signal?: AbortSignal): Promise<RegionDetail> {
  const body = await getJson(apiUrl(`regions/${String(id)}`), signal);
  if (!isRegion(body) || !Array.isArray((body as Partial<RegionDetail>).ancestors)) {
    throw new ApiError('La API respondió con un formato que no se reconoce.', 'bad_format');
  }
  return body as RegionDetail;
}
