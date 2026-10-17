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

// Tope de la API por página (backend: MAX_PAGE_SIZE de regiones).
const REGIONS_PAGE_SIZE = 200;
// Para los filtros encadenados: los 32 estados y hasta 570 municipios de un
// estado caben de sobra. Un municipio puede tener miles de localidades: se
// muestran las primeras y para las demás está el buscador.
export const MAX_FILTER_OPTIONS = 600;

async function collect(
  path: string,
  query: Record<string, string>,
  max: number,
  signal?: AbortSignal,
): Promise<Region[]> {
  const all: Region[] = [];
  let cursor: string | null = null;
  do {
    const params = new URLSearchParams({ ...query, limit: String(REGIONS_PAGE_SIZE) });
    if (cursor) params.set('cursor', cursor);
    const body = (await requestJson(`${apiUrl(path)}?${params.toString()}`, {
      signal,
    })) as { items?: unknown; next_cursor?: unknown } | null;
    if (!Array.isArray(body?.items) || !body.items.every(isRegion)) throw badFormat();
    all.push(...body.items);
    cursor = typeof body.next_cursor === 'string' ? body.next_cursor : null;
  } while (cursor && all.length < max);
  return all.slice(0, max);
}

/**
 * Todas las regiones de un nivel (por ejemplo, los 32 estados), en orden alfabético.
 *
 * @param level Nivel.
 * @param signal Señal para cancelar.
 */
export function listRegionsByLevel(level: RegionLevel, signal?: AbortSignal): Promise<Region[]> {
  return collect('regions', { level }, MAX_FILTER_OPTIONS, signal);
}

/**
 * Hijas de una región (municipios de un estado, localidades de un municipio),
 * hasta `MAX_FILTER_OPTIONS`, en orden alfabético.
 *
 * @param regionId Región madre.
 * @param signal Señal para cancelar.
 */
export function listChildRegions(regionId: number, signal?: AbortSignal): Promise<Region[]> {
  return collect(`regions/${String(regionId)}/children`, {}, MAX_FILTER_OPTIONS, signal);
}
