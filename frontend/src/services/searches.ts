/**
 * Servicio de búsquedas y notas (`/api/v1/searches`, `/api/v1/articles`; docs/api.md).
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2). Aquí se
 * estima, se lanza y se sigue una búsqueda, y se leen sus notas, su mapa de
 * calor y el historial. La forma de cada respuesta se revisa en lo esencial;
 * si no coincide, se lanza `badFormat` en lugar de dibujar datos a medias.
 */
import { apiUrl } from '../config/api';
import type { PlannedQuery } from './concepts';
import { badFormat, requestJson } from './http';

/** Qué buscar (cuerpo de `/searches/estimate` y `/searches`). */
export interface SearchInput {
  concept_ids: number[];
  region_id: number;
  /** Últimos N días; se ignora si vienen las dos fechas. */
  days?: number;
  date_from?: string;
  date_to?: string;
  /** Fuentes encendidas (`/sources`); sin mandar, las de por defecto (F12.2). */
  providers?: string[];
}

export interface ConceptRef {
  id: number;
  name: string;
}

export interface SearchEstimate {
  concepts: ConceptRef[];
  region_id: number;
  region: string;
  date_from: string;
  date_to: string;
  queries: PlannedQuery[];
  credits: number;
  credits_month: number;
  credits_limit: number;
  over_limit: boolean;
  llm: {
    provider: string;
    model: string;
    configured: boolean;
    max_articles: number;
    max_cost_usd: number;
  };
  /** Fuentes con las que se buscaría (F12.2). */
  providers?: string[];
}

export type SearchStatus = 'pending' | 'running' | 'completed' | 'partial' | 'failed';

export interface SearchProgress {
  stage?: string;
  articles?: number;
  reused?: number;
  enriched?: number;
  fallback?: number;
  in_region?: number;
  out_of_region?: number;
  unlocated?: number;
  skipped_by_cap?: number;
}

export interface Search {
  search_id: string;
  status: SearchStatus;
  region_id: number;
  region_code: string;
  region_name: string;
  date_from: string;
  date_to: string;
  concepts: ConceptRef[];
  progress: SearchProgress;
  queries_planned: number;
  credits_estimated: number;
  credits_used: number;
  llm_tokens_in: number;
  llm_tokens_out: number;
  llm_cost_usd: number;
  results_count: number;
  error_summary: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  /**
   * Fuentes con las que se hizo (F12.2). Vacía en búsquedas de antes de F12.2,
   * que usaron todas las configuradas.
   */
  providers?: string[];
  /**
   * Quién la lanzó (F12.8): `manual` (una persona) o `automatic` (el monitor
   * FGR a las 07:00, 15:00 y 23:00). Ausente en respuestas de antes de F12.8.
   */
  trigger?: 'manual' | 'automatic';
  /** Hora programada de una corrida automática (UTC). */
  scheduled_for?: string | null;
}

export interface Judgement {
  concept_id: number;
  name: string;
  is_relevant: boolean;
  relevance_score: number;
  relevance_reason: string | null;
}

export type Precision = 'country' | 'state' | 'municipality' | 'locality' | 'unknown';

export interface ArticleLocation {
  mention: string;
  role: 'event' | 'mentioned';
  precision: Precision;
  confidence: number;
  is_primary: boolean;
  region_id: number | null;
  region_code: string | null;
  place: string | null;
  lon: number | null;
  lat: number | null;
}

export interface Article {
  article_id: number;
  title: string;
  source_name: string | null;
  source_domain: string | null;
  url: string;
  published_at: string | null;
  summary: string | null;
  event_type: string | null;
  event_date: string | null;
  extraction_status: string;
  enrichment_status: string;
  concepts: Judgement[];
  primary_location: ArticleLocation | null;
  in_region: boolean | null;
  providers: string[];
  /**
   * Historia: id de la primera nota del mismo hecho en varios medios
   * (ADR-0026); `null` o ausente si la nota está sola.
   */
  story_id?: number | null;
  /**
   * Categoría (el delito) que eligió la IA (ADR-0029); `null` o ausente si
   * todavía no se clasifica. Colores y símbolos llegan después.
   */
  category?: ArticleCategory | null;
  /** Etiqueta libre que propuso la IA («robo de combustible»). */
  category_raw?: string | null;
  /**
   * Quién actúa en el hecho según la IA (ADR-0030); `null` o ausente si
   * todavía no se clasifica. La relevancia de `concepts` ya lo toma en cuenta.
   */
  authority?: Authority | null;
}

/** Quién actúa en una nota (F12.5): la FGR federal, solo mencionada, una fiscalía estatal… */
export type Authority = 'fgr' | 'fgr_mencion' | 'estatal' | 'otra' | 'sin_dato';

export interface ArticleCategory {
  id: number;
  name: string;
  color: string | null;
  symbol: string | null;
}

export interface ArticleDetail extends Article {
  locations: ArticleLocation[];
  first_seen_at: string;
  llm_model: string | null;
  prompt_version: string | null;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export type InRegionFilter = 'true' | 'false' | 'none';
export type AggregateLevel = 'country' | 'state' | 'municipality';

export interface ArticleFilters {
  /** `all` incluye las notas no relevantes. */
  relevant?: 'true' | 'all';
  in_region?: InRegionFilter;
  precision?: Precision[];
  concept_id?: number;
}

export interface AggregateItem {
  region_id: number;
  code: string;
  name: string;
  count: number;
  lon: number;
  lat: number;
}

export interface Aggregates {
  level: AggregateLevel;
  items: AggregateItem[];
  coarser: number;
  abroad: number;
  unlocated: number;
  total: number;
}

// Notas por página al pedir todas las de una búsqueda: el tope de la API.
// Una búsqueda trae como máximo ~150 notas enriquecidas (ADR-0015).
const ARTICLES_PAGE_SIZE = 200;
// Historial: una pantalla cómoda.
const HISTORY_PAGE_SIZE = 20;

/** Si el valor es un objeto (no nulo): base de las validaciones de forma. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isEstimate(value: unknown): value is SearchEstimate {
  return (
    isRecord(value) &&
    Array.isArray(value.queries) &&
    typeof value.credits === 'number' &&
    typeof value.over_limit === 'boolean' &&
    isRecord(value.llm)
  );
}

function isSearch(value: unknown): value is Search {
  return (
    isRecord(value) &&
    typeof value.search_id === 'string' &&
    typeof value.status === 'string' &&
    isRecord(value.progress)
  );
}

/** Si el valor tiene la forma de una nota de la API (también la usan los casos). */
export function isArticle(value: unknown): value is Article {
  return (
    isRecord(value) &&
    typeof value.article_id === 'number' &&
    typeof value.title === 'string' &&
    Array.isArray(value.concepts) &&
    Array.isArray(value.providers)
  );
}

/** Si el valor es una página `{items, next_cursor}` cuyos elementos pasan `guard`. */
export function isPage<T>(value: unknown, guard: (item: unknown) => item is T): value is Page<T> {
  return isRecord(value) && Array.isArray(value.items) && value.items.every(guard);
}

/**
 * Qué haría una búsqueda y cuánto costaría, sin gastar nada.
 *
 * @throws {ApiError} Con el mensaje en español (concepto o región inválidos...).
 */
export async function estimateSearch(input: SearchInput, signal?: AbortSignal) {
  const data = await requestJson(apiUrl('searches/estimate'), {
    method: 'POST',
    body: input,
    signal,
  });
  if (!isEstimate(data)) throw badFormat();
  return data;
}

/**
 * Lanza la búsqueda (gasta créditos y tokens). Responde con su id.
 *
 * @throws {ApiError} `credit_limit_reached` (409), `llm_not_configured` (503)...
 */
export async function startSearch(input: SearchInput): Promise<string> {
  const data = await requestJson(apiUrl('searches'), { method: 'POST', body: input });
  if (!isRecord(data) || typeof data.search_id !== 'string') throw badFormat();
  return data.search_id;
}

/** Estado, avance y costo de una búsqueda. */
export async function getSearch(searchId: string, signal?: AbortSignal): Promise<Search> {
  const data = await requestJson(apiUrl(`searches/${encodeURIComponent(searchId)}`), { signal });
  if (!isSearch(data)) throw badFormat();
  return data;
}

/** Una página del historial, de la más reciente a la más vieja. */
export async function listSearches(
  cursor: string | null,
  signal?: AbortSignal,
): Promise<Page<Search>> {
  const params = new URLSearchParams({ limit: String(HISTORY_PAGE_SIZE) });
  if (cursor) params.set('cursor', cursor);
  const data = await requestJson(`${apiUrl('searches')}?${params.toString()}`, { signal });
  if (!isPage(data, isSearch)) throw badFormat();
  return data;
}

/**
 * Arma los parámetros de URL de los filtros de notas.
 *
 * @example articleParams({ in_region: 'false', precision: ['state'] }).toString()
 * // 'in_region=false&precision=state'
 */
export function articleParams(filters: ArticleFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.relevant) params.set('relevant', filters.relevant);
  if (filters.in_region) params.set('in_region', filters.in_region);
  for (const precision of filters.precision ?? []) params.append('precision', precision);
  if (filters.concept_id !== undefined) params.set('concept_id', String(filters.concept_id));
  return params;
}

/**
 * Todas las notas de una búsqueda con esos filtros (sigue el cursor).
 *
 * Una búsqueda trae pocas notas (≤ ~150): la lista y el globo las usan todas.
 */
export async function listAllArticles(
  searchId: string,
  filters: ArticleFilters,
  signal?: AbortSignal,
): Promise<Article[]> {
  const all: Article[] = [];
  let cursor: string | null = null;
  do {
    const params = articleParams(filters);
    params.set('limit', String(ARTICLES_PAGE_SIZE));
    if (cursor) params.set('cursor', cursor);
    const data = await requestJson(
      `${apiUrl(`searches/${encodeURIComponent(searchId)}/articles`)}?${params.toString()}`,
      { signal },
    );
    if (!isPage(data, isArticle)) throw badFormat();
    all.push(...data.items);
    cursor = data.next_cursor;
  } while (cursor);
  return all;
}

/** Conteo de notas por región, para el mapa de calor. */
export async function getAggregates(
  searchId: string,
  level: AggregateLevel,
  signal?: AbortSignal,
): Promise<Aggregates> {
  const data = await requestJson(
    `${apiUrl(`searches/${encodeURIComponent(searchId)}/aggregates`)}?level=${level}`,
    { signal },
  );
  if (!isRecord(data) || !Array.isArray(data.items) || typeof data.total !== 'number') {
    throw badFormat();
  }
  return data as unknown as Aggregates;
}

/** Detalle de una nota con todas sus menciones de lugar. */
export async function getArticle(articleId: number, signal?: AbortSignal): Promise<ArticleDetail> {
  const data = await requestJson(apiUrl(`articles/${String(articleId)}`), { signal });
  if (!isArticle(data) || !Array.isArray((data as unknown as ArticleDetail).locations)) {
    throw badFormat();
  }
  return data as ArticleDetail;
}

/** Una búsqueda ya no cambia cuando terminó (bien, a medias o con falla). */
export function isFinished(status: SearchStatus): boolean {
  return status === 'completed' || status === 'partial' || status === 'failed';
}

/**
 * Quita una búsqueda del historial. Es reversible (`restoreSearch`) y sus notas
 * siguen en el sistema.
 *
 * @throws {ApiError} `search_forbidden` si es una búsqueda manual de otra persona.
 */
export async function deleteSearch(searchId: string): Promise<void> {
  await requestJson(apiUrl(`searches/${encodeURIComponent(searchId)}`), { method: 'DELETE' });
}

/** Devuelve una búsqueda al historial («Deshacer»). */
export async function restoreSearch(searchId: string): Promise<void> {
  await requestJson(apiUrl(`searches/${encodeURIComponent(searchId)}/restore`), {
    method: 'POST',
  });
}
