/**
 * Servicio de conceptos: CRUD, "Probar concepto" y la propuesta de frases de
 * la IA (`/api/v1/concepts`).
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2). Las
 * reglas (nombre único, palabras repetidas, caracteres prohibidos) las
 * aplica el backend; aquí solo se traducen sus errores por campo para
 * mostrarlos junto al campo correcto.
 */
import { apiUrl } from '../config/api';
import { ApiError, badFormat, requestJson } from './http';
import type { RegionDetail } from './regions';

/**
 * Cómo se busca un concepto (ADR-0109): `exact` manda cada frase entre
 * comillas; `open` la manda sola y sin comillas, como en Google.
 */
export type QueryMode = 'exact' | 'open';

export interface Concept {
  id: number;
  name: string;
  /** En un concepto `open`, lo que el analista busca en sus palabras. */
  description: string;
  keywords: string[];
  exclude_terms: string[];
  /** #RRGGBB */
  color: string;
  /** Si aparece en el panel de búsqueda. */
  is_active: boolean;
  query_mode: QueryMode;
  /** «frases exactas» o «como en Google». */
  query_mode_label: string;
  /**
   * Si es el tema general de una subdivisión (ADR-0038): el id de esa
   * subdivisión en `/categories`; `null` en los demás, como la FGR.
   */
  category_id: number | null;
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
  query_mode: QueryMode;
}

/** Lo que la IA propone a partir de lo que el analista escribió (ADR-0109). */
export interface TermSuggestion {
  name: string;
  /** Frases tipo titular, de la que más notas traería a la que menos. */
  keywords: string[];
  exclude_terms: string[];
  query_mode: QueryMode;
  model: string;
  /** Lo que costó la propuesta, en dólares. */
  cost_usd: number;
}

/** Campos que cambian en una edición; los que faltan no cambian. */
export type ConceptPatch = Partial<ConceptInput>;

export type Provider = 'searchapi' | 'google_news_rss' | 'gdelt' | 'indice_local';

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
  return withDefaults(body);
}

type RawConcept = Omit<Concept, 'category_id' | 'query_mode' | 'query_mode_label'> &
  Partial<Pick<Concept, 'category_id' | 'query_mode' | 'query_mode_label'>>;

/**
 * Las respuestas de antes del 02/11/2026 no traen `category_id` (no son
 * temas), y las de antes del 17/11/2026 no traen el modo (son exactos).
 */
function withDefaults(concept: Concept): Concept {
  const raw = concept as RawConcept;
  return {
    ...raw,
    category_id: raw.category_id ?? null,
    query_mode: raw.query_mode ?? 'exact',
    query_mode_label: raw.query_mode_label ?? 'frases exactas',
  };
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
    all.push(...body.items.map(withDefaults));
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

function isSuggestion(value: unknown): value is TermSuggestion {
  if (typeof value !== 'object' || value === null) return false;
  const s = value as Record<string, unknown>;
  return (
    typeof s.name === 'string' &&
    Array.isArray(s.keywords) &&
    Array.isArray(s.exclude_terms) &&
    (s.query_mode === 'open' || s.query_mode === 'exact') &&
    typeof s.cost_usd === 'number'
  );
}

/**
 * La IA propone nombre, frases y exclusiones a partir de lo que se escribió.
 *
 * No guarda el concepto: la persona revisa la propuesta antes. Cada petición
 * cuesta unos 0.0001 USD y queda en la bitácora (ADR-0109).
 *
 * @param description Lo que la persona quiere seguir, en sus palabras.
 * @returns La propuesta.
 * @throws {ApiError} `invalid_concept` si el texto es muy corto (campo
 *   `description`), `empty_suggestion`, `term_suggestion_failed` o
 *   `llm_not_configured`.
 */
/**
 * «Guardar como concepto» una búsqueda rápida (ADR-0110): deja de estar oculto.
 *
 * @throws {ApiError} `concept_name_taken` (409) si ya hay uno con ese nombre.
 */
export async function keepConcept(id: number): Promise<Concept> {
  return asConcept(await requestJson(apiUrl(`concepts/${String(id)}/keep`), { method: 'POST' }));
}

export async function suggestTerms(description: string): Promise<TermSuggestion> {
  const body = await requestJson(apiUrl('concepts/suggest'), {
    method: 'POST',
    body: { description },
  });
  if (!isSuggestion(body)) throw badFormat();
  return body;
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
