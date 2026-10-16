/**
 * Servicio de regiones: búsqueda y detalle (`/api/v1/regions`).
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2). Las
 * peticiones pasan por el cliente compartido (`http.ts`), que traduce el
 * formato uniforme de error a un `ApiError` con el mensaje en español.
 */
import { apiUrl } from '../config/api';
import type { RegionLevel } from '../map/style';
import { ApiError, badFormat, requestJson } from './http';

export { ApiError };

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
  const body = (await requestJson(url, { signal })) as { items?: unknown } | null;
  if (!Array.isArray(body?.items) || !body.items.every(isRegion)) {
    throw badFormat();
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
  const body = await requestJson(apiUrl(`regions/${String(id)}`), { signal });
  if (!isRegion(body) || !Array.isArray((body as Partial<RegionDetail>).ancestors)) {
    throw badFormat();
  }
  return body as RegionDetail;
}
