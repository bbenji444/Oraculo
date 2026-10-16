/**
 * Servicio de conceptos: CRUD y "Probar concepto" (`/api/v1/concepts`).
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2). Las
 * reglas (nombre único, palabras repetidas, caracteres prohibidos) las
 * aplica el backend; aquí solo se traducen sus errores por campo para
 * mostrarlos junto al campo correcto.
 */
import { apiUrl } from '../config/api';
import { ApiError, badFormat, requestJson } from './http';
import type { RegionDetail } from './regions';

export interface Concept {
  id: number;
  name: string;
  description: string;
  keywords: string[];
  exclude_terms: string[];
  /** #RRGGBB */
  color: string;
  /** Si aparece en el panel de búsqueda. */
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

/** Datos del formulario (crear, o probar sin guardar). */
export interface ConceptInput {
  name: string;
  description: string;
  keywords: string[];
  exclude_terms: string[];
  color: string;
  is_active: boolean;
}

/** Campos que cambian en una edición; los que faltan no cambian. */
export type ConceptPatch = Partial<ConceptInput>;

export type Provider = 'searchapi' | 'google_news_rss' | 'gdelt';

export interface PlannedQuery {
  provider: Provider;
  provider_label: string;
  /** Texto exacto que se enviaría al proveedor. */
  text: string;
  keywords: string[];
  filters: { country: string; language: string; period: string };
  estimated_credits: number;
}

export interface QueryPreview {
  concept_name: string;
  region: RegionDetail;
  window: { date_from: string; date_to: string; description: string };
  queries: PlannedQuery[];
  total_queries: number;
  total_credits: number;
}

/** Problemas de validación por campo, como los entrega la API. */
export type FieldErrors = Partial<Record<keyof ConceptInput, string[]>>;

// Los conceptos son pocas decenas: una página de 200 los trae todos casi
// siempre; si hubiera más, se siguen pidiendo con el cursor.
const PAGE_SIZE = 200;

function isConcept(value: unknown): value is Concept {
  if (typeof value !== 'object' || value === null) return false;
  const c = value as Record<string, unknown>;
  return (
    typeof c.id === 'number' &&
    typeof c.name === 'string' &&
    Array.isArray(c.keywords) &&
    Array.isArray(c.exclude_terms) &&
    typeof c.color === 'string' &&
    typeof c.is_active === 'boolean'
  );
}

function asConcept(body: unknown): Concept {
  if (!isConcept(body)) throw badFormat();
  return body;
}

/**
 * Todos los conceptos vigentes, en orden alfabético.
 *
 * @param signal Señal para cancelar.
 * @returns Los conceptos (activos e inactivos).
 * @throws {ApiError} Si la API falla.
 */
export async function listConcepts(signal?: AbortSignal): Promise<Concept[]> {
  const all: Concept[] = [];
  let cursor: string | null = null;
  do {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
    if (cursor) params.set('cursor', cursor);
    const body = (await requestJson(`${apiUrl('concepts')}?${params.toString()}`, {
      signal,
    })) as { items?: unknown; next_cursor?: unknown } | null;
    if (!Array.isArray(body?.items) || !body.items.every(isConcept)) throw badFormat();
    all.push(...body.items);
    cursor = typeof body.next_cursor === 'string' ? body.next_cursor : null;
  } while (cursor);
  return all;
}

/**
 * Crea un concepto.
 *
 * @param input Datos del formulario.
 * @returns El concepto guardado.
 * @throws {ApiError} `invalid_concept` (ver `fieldErrors`) o `concept_name_taken`.
 */
export async function createConcept(input: ConceptInput): Promise<Concept> {
  return asConcept(await requestJson(apiUrl('concepts'), { method: 'POST', body: input }));
}

/**
 * Edita un concepto (también activar o desactivar).
 *
 * @param id Id del concepto.
 * @param patch Campos que cambian.
 * @returns El concepto como quedó.
 * @throws {ApiError} `invalid_concept`, `concept_name_taken` o `concept_not_found`.
 */
export async function updateConcept(id: number, patch: ConceptPatch): Promise<Concept> {
  return asConcept(
    await requestJson(apiUrl(`concepts/${String(id)}`), { method: 'PATCH', body: patch }),
  );
}

/**
 * Borra un concepto (lógico si ya se usó en búsquedas).
 *
 * @param id Id del concepto.
 * @throws {ApiError} `concept_not_found` si ya no existe.
 */
export async function deleteConcept(id: number): Promise<void> {
  await requestJson(apiUrl(`concepts/${String(id)}`), { method: 'DELETE' });
}

/**
 * Consultas que generaría un concepto, sin gastar créditos.
 *
 * Con `conceptId` prueba el concepto guardado; sin él, prueba el borrador
 * del formulario tal como está (historia H2: probar antes de guardar).
 *
 * @param args Región, rango en días y el concepto (guardado o borrador).
 * @returns Las consultas por proveedor, con filtros y créditos estimados.
 * @throws {ApiError} Si el borrador no es válido, la región no existe o el rango no aplica.
 */
export async function previewQueries(args: {
  regionId: number;
  days: number;
  conceptId?: number;
  draft?: ConceptInput;
}): Promise<QueryPreview> {
  const params = new URLSearchParams({ region_id: String(args.regionId), days: String(args.days) });
  const path =
    args.conceptId === undefined
      ? 'concepts/preview'
      : `concepts/${String(args.conceptId)}/preview`;
  const body = (await requestJson(`${apiUrl(path)}?${params.toString()}`, {
    method: 'POST',
    body: args.conceptId === undefined ? args.draft : undefined,
  })) as QueryPreview | null;
  if (!body || !Array.isArray(body.queries)) throw badFormat();
  return body;
}

/**
 * Agrupa por campo los problemas de validación de un error de la API.
 *
 * @param error Error recibido al guardar o probar.
 * @returns Mensajes por campo; vacío si el error no es de validación.
 */
export function fieldErrors(error: unknown): FieldErrors {
  if (!(error instanceof ApiError) || error.code !== 'invalid_concept') return {};
  const problems = error.details.problemas;
  const result: FieldErrors = {};
  if (!Array.isArray(problems)) return result;
  for (const problem of problems as { campo?: unknown; mensaje?: unknown }[]) {
    if (typeof problem.campo !== 'string' || typeof problem.mensaje !== 'string') continue;
    const field = problem.campo as keyof ConceptInput;
    (result[field] ??= []).push(problem.mensaje);
  }
  return result;
}
