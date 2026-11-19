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
  /**
   * Subdivisiones (ADR-0038): a la FGR se le exige además una palabra del tema
   * de cada una («FGR · Homicidio»).
   */
  category_ids?: number[];
}

export interface ConceptRef {
  id: number;
  name: string;
  /** Subdivisiones con que se buscó; falta en respuestas de antes del 02/11/2026. */
  subdivision_ids?: number[];
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

/** `cancelled`: quien la lanzó la detuvo (19/11/2026, ADR-0118). */
export type SearchStatus = 'pending' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';

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
  /**
   * Aviso del worker para el analista si Google web no pudo buscar (sin
   * créditos o error de la cuenta de SearchApi, ADR-0115): la búsqueda siguió
   * con las demás fuentes. Falta si no hubo nada que avisar.
   */
  notice?: string;
}

export interface Search {
  search_id: string;
  /** Quién la lanzó (`monitor-automatico` en las corridas automáticas). */
  user_id?: string;
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
  /**
   * Horas que cubre una corrida automática: desde la corrida anterior hasta
   * su hora (28/10/2026). Vacías en las manuales y en las corridas de antes.
   */
  window_start?: string | null;
  window_end?: string | null;
}

/**
 * Qué tan de cerca toca la nota lo que se buscó (ADR-0117), según el puntaje
 * de la IA: `relevant` (0.8 o más), `unconfirmed` (relevante «por
 * confirmar», 0.6 a 0.79), `related` («cercana»: mismo tema, otra entidad o
 * lugar, o de pasada; 0.3 a 0.59) y `unrelated` («ajena»: nada que ver).
 */
export type RelevanceBand = 'relevant' | 'unconfirmed' | 'related' | 'unrelated';

export interface Judgement {
  concept_id: number;
  name: string;
  /** La relevancia final, con el umbral y la regla FGR ya aplicados (ADR-0030). */
  is_relevant: boolean;
  relevance_score: number;
  relevance_reason: string | null;
  /**
   * La banda que calcula el servidor (ADR-0117). Falta en respuestas de antes
   * del 18/11/2026: la pantalla la deduce del puntaje (`Explore/relevance.ts`).
   */
  relevance_band?: RelevanceBand;
}

/**
 * Dónde se publicó la nota (ADR-0117): un medio de noticias, una red social
 * o cualquier otro sitio web. Los valores son los mismos que manda la API.
 */
export type Platform =
  'news' | 'facebook' | 'x' | 'youtube' | 'instagram' | 'tiktok' | 'reddit' | 'telegram' | 'web';

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
   * Dónde se publicó (ADR-0117): Facebook, X, YouTube… o `news` si es de un
   * medio. Falta en respuestas de antes del 18/11/2026: entonces se toma
   * como noticia (`Explore/platforms.ts`).
   */
  platform?: Platform;
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

/** Búsqueda rápida (ADR-0110): un texto en lugar de conceptos. */
export type QuickSearchInput = Omit<SearchInput, 'concept_ids' | 'category_ids'> & {
  /** Lo que se busca, en palabras del analista. */
  text: string;
};

/** Lo que responde una búsqueda rápida recién lanzada. */
export interface QuickSearchStarted {
  searchId: string;
  /** El concepto oculto que la sostiene: «Guardar como concepto» lo usa. */
  conceptId: number;
  conceptName: string;
  /** El lugar que nombró el texto («en Jalisco») si se buscó ahí; `null` si se buscó en la región elegida. */
  placeRegionId: number | null;
  /**
   * Aviso si se buscó con menos fuentes de las pedidas («Sin créditos de
   * Google web: se buscó en noticias», ADR-0115); `null` si no hubo.
   */
  notice: string | null;
}

/** Quita espacios y deja `null` si el aviso viene vacío o no es texto. */
function noticeText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

/**
 * Los avisos que hay que mostrarle al analista de una búsqueda: el que dio
 * la búsqueda rápida al lanzarse (si es esta misma búsqueda) y el que deja el
 * worker en su avance, sin repetir el mismo texto (ADR-0115).
 *
 * @param search La búsqueda, con su avance.
 * @param launched Lo que respondió el lanzamiento de la búsqueda rápida, si se conoce.
 * @returns Los avisos, primero el del lanzamiento; vacío si no hay.
 * @example searchNotices(busqueda, { searchId: busqueda.search_id, notice: 'Sin créditos…' })
 * // ['Sin créditos…']
 */
export function searchNotices(
  search: Pick<Search, 'search_id' | 'progress'>,
  launched: { searchId: string; notice: string | null } | null,
): string[] {
  const fromLaunch = launched?.searchId === search.search_id ? noticeText(launched.notice) : null;
  const fromWorker = noticeText(search.progress.notice);
  return [...new Set([fromLaunch, fromWorker].filter((n): n is string => n !== null))];
}

/**
 * Lanza una búsqueda rápida: la IA propone las frases y se busca como en
 * Google, sin guardar un concepto (gasta tokens de la IA).
 *
 * @throws {ApiError} los mismos de `startSearch`, o `invalid_concept` si el
 *   texto es muy corto o muy largo.
 */
export async function startQuickSearch(input: QuickSearchInput): Promise<QuickSearchStarted> {
  const data = await requestJson(apiUrl('searches/quick'), { method: 'POST', body: input });
  if (
    !isRecord(data) ||
    typeof data.search_id !== 'string' ||
    !isRecord(data.concept) ||
    typeof data.concept.id !== 'number' ||
    typeof data.concept.name !== 'string'
  ) {
    throw badFormat();
  }
  const place = isRecord(data.place_region) ? data.place_region.id : null;
  return {
    searchId: data.search_id,
    conceptId: data.concept.id,
    conceptName: data.concept.name,
    placeRegionId: typeof place === 'number' ? place : null,
    notice: noticeText(data.notice),
  };
}

/** Estado, avance y costo de una búsqueda. */
export async function getSearch(searchId: string, signal?: AbortSignal): Promise<Search> {
  const data = await requestJson(apiUrl(`searches/${encodeURIComponent(searchId)}`), { signal });
  if (!isSearch(data)) throw badFormat();
  return data;
}

/** Una página del historial, de la más reciente a la más vieja. */
export type HistoryScope = 'mine' | 'all';

export async function listSearches(
  cursor: string | null,
  signal?: AbortSignal,
  scope: HistoryScope = 'mine',
): Promise<Page<Search>> {
  const params = new URLSearchParams({ limit: String(HISTORY_PAGE_SIZE) });
  if (cursor) params.set('cursor', cursor);
  // «all» solo lo respeta el servidor para superusuarios (ADR-0042).
  if (scope === 'all') params.set('scope', 'all');
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

/** Una búsqueda ya no cambia cuando terminó (bien, a medias, con falla o cancelada). */
export function isFinished(status: SearchStatus): boolean {
  return (
    status === 'completed' || status === 'partial' || status === 'failed' || status === 'cancelled'
  );
}

/**
 * Las subdivisiones con que se hizo una búsqueda («FGR · Homicidio»), sin repetir.
 *
 * @example subdivisionsOf({ concepts: [{ id: 13, name: 'FGR', subdivision_ids: [5] }] }) // [5]
 */
export function subdivisionsOf(search: Pick<Search, 'concepts'>): number[] {
  return [...new Set(search.concepts.flatMap((c) => c.subdivision_ids ?? []))];
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

/**
 * Si ya no hay nada que volver a leer: terminó y, si se canceló, el worker ya
 * se detuvo y guardó lo gastado (pone `finished_at`; ADR-0118).
 */
export function isSettled(search: Pick<Search, 'status' | 'finished_at'>): boolean {
  if (search.status === 'cancelled') return search.finished_at !== null;
  return isFinished(search.status);
}

/**
 * Detiene una búsqueda que todavía corre (ADR-0118). El worker para en su
 * siguiente revisión y guarda lo que alcanzó a gastar.
 *
 * @throws ApiError 403 si es de otra persona o automática; 409 si ya terminó.
 */
export async function cancelSearch(searchId: string): Promise<void> {
  await requestJson(apiUrl(`searches/${encodeURIComponent(searchId)}/cancel`), {
    method: 'POST',
  });
}

/** Devuelve una búsqueda al historial («Deshacer»). */
export async function restoreSearch(searchId: string): Promise<void> {
  await requestJson(apiUrl(`searches/${encodeURIComponent(searchId)}/restore`), {
    method: 'POST',
  });
}
