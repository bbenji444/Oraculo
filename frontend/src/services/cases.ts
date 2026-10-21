/**
 * Servicio de casos de investigación (`/api/v1/cases`; docs/api.md, Fase 9.3).
 *
 * Cada persona ve solo sus casos: un caso ajeno responde `case_not_found`,
 * igual que uno que no existe. Abrir un caso (`getCase`) queda en la bitácora
 * del servidor como `case.viewed`.
 *
 * No hace: no guarda estado (eso es TanStack Query en `hooks/useCases`).
 */
import { apiUrl } from '../config/api';
import { ApiError, badFormat, requestJson } from './http';
import { type Article, isArticle, isPage, isRecord } from './searches';

export type CaseStatus = 'open' | 'closed' | 'archived';
export type Sensitivity = 'normal' | 'restricted' | 'confidential';
export type CaseRole = 'owner' | 'editor' | 'viewer';

/** Un caso, con el rol de quien lo pide. */
export interface Case {
  id: string;
  name: string;
  description: string;
  status: CaseStatus;
  status_label: string;
  sensitivity: Sensitivity;
  sensitivity_label: string;
  created_by: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  article_count: number;
  role: CaseRole | null;
  /** Con `containsArticle`: si el caso ya tiene esa nota. */
  has_article: boolean | null;
}

/** Datos del formulario de un caso. */
export interface CaseInput {
  name: string;
  description: string;
  sensitivity: Sensitivity;
}

/** Cambios a un caso; `status` cierra, archiva o reabre. */
export type CasePatch = Partial<CaseInput> & { status?: CaseStatus };

/** Mensajes de validación por campo (`invalid_case`). */
export type CaseFieldErrors = Partial<Record<keyof CaseInput, string[]>>;

// Página grande: una persona tiene pocos casos y la lista los muestra todos.
const CASES_PAGE_SIZE = 200;
// Notas por página al pedir las de un caso (el máximo de la API).
const ARTICLES_PAGE_SIZE = 200;

function isCase(value: unknown): value is Case {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.status === 'string' &&
    typeof value.article_count === 'number'
  );
}

function asCase(value: unknown): Case {
  if (!isCase(value)) throw badFormat();
  return value;
}

function caseUrl(id: string, rest = ''): string {
  return apiUrl(`cases/${encodeURIComponent(id)}${rest}`);
}

/**
 * Mis casos, del cambio más reciente al más viejo (sigue el cursor).
 *
 * @param options.status Solo ese estado; sin él, abiertos y cerrados.
 * @param options.containsArticle Si viene, cada caso dice si ya tiene esa nota.
 */
export async function listCases(
  options: { status?: CaseStatus; containsArticle?: number } = {},
  signal?: AbortSignal,
): Promise<Case[]> {
  const all: Case[] = [];
  let cursor: string | null = null;
  do {
    const params = new URLSearchParams({ limit: String(CASES_PAGE_SIZE) });
    if (options.status) params.set('status', options.status);
    if (options.containsArticle !== undefined) {
      params.set('contains_article', String(options.containsArticle));
    }
    if (cursor) params.set('cursor', cursor);
    const data = await requestJson(`${apiUrl('cases')}?${params.toString()}`, { signal });
    if (!isPage(data, isCase)) throw badFormat();
    all.push(...data.items);
    cursor = data.next_cursor;
  } while (cursor);
  return all;
}

/**
 * Abre un caso (queda en la bitácora del servidor).
 *
 * @throws {ApiError} `case_not_found` si no existe o no es de la persona.
 */
export async function getCase(id: string, signal?: AbortSignal): Promise<Case> {
  return asCase(await requestJson(caseUrl(id), { signal }));
}

/**
 * Crea un caso; quien lo crea queda como dueño.
 *
 * @throws {ApiError} `invalid_case` (ver `caseFieldErrors`).
 */
export async function createCase(input: CaseInput): Promise<Case> {
  return asCase(await requestJson(apiUrl('cases'), { method: 'POST', body: input }));
}

/**
 * Edita, cierra, archiva o reabre un caso.
 *
 * @throws {ApiError} `invalid_case`, `case_forbidden` o `case_closed`.
 */
export async function updateCase(id: string, patch: CasePatch): Promise<Case> {
  return asCase(await requestJson(caseUrl(id), { method: 'PATCH', body: patch }));
}

/** Todas las notas de un caso, de la más reciente a la más vieja. */
export async function listCaseArticles(id: string, signal?: AbortSignal): Promise<Article[]> {
  const all: Article[] = [];
  let cursor: string | null = null;
  do {
    const params = new URLSearchParams({ limit: String(ARTICLES_PAGE_SIZE) });
    if (cursor) params.set('cursor', cursor);
    const data = await requestJson(`${caseUrl(id, '/articles')}?${params.toString()}`, {
      signal,
    });
    if (!isPage(data, isArticle)) throw badFormat();
    all.push(...data.items);
    cursor = data.next_cursor;
  } while (cursor);
  return all;
}

/**
 * Agrega una nota al caso; si ya estaba, no pasa nada.
 *
 * @returns `true` si se agregó; `false` si ya estaba.
 * @throws {ApiError} `case_closed`, `case_forbidden` o `article_not_found`.
 */
export async function addCaseArticle(id: string, articleId: number): Promise<boolean> {
  const data = await requestJson(caseUrl(id, '/articles'), {
    method: 'POST',
    body: { article_id: articleId },
  });
  if (!isRecord(data) || typeof data.added !== 'boolean') throw badFormat();
  return data.added;
}

/** Quita una nota del caso (la noticia sigue en el sistema). */
export async function removeCaseArticle(id: string, articleId: number): Promise<void> {
  await requestJson(caseUrl(id, `/articles/${String(articleId)}`), { method: 'DELETE' });
}

/**
 * Agrupa por campo los problemas de validación de un caso.
 *
 * @param error Error recibido al guardar.
 * @returns Mensajes por campo; vacío si el error no es de validación.
 */
export function caseFieldErrors(error: unknown): CaseFieldErrors {
  if (!(error instanceof ApiError) || error.code !== 'invalid_case') return {};
  const problems = error.details.problemas;
  const result: CaseFieldErrors = {};
  if (!Array.isArray(problems)) return result;
  for (const problem of problems as { campo?: unknown; mensaje?: unknown }[]) {
    if (typeof problem.campo !== 'string' || typeof problem.mensaje !== 'string') continue;
    const field = problem.campo as keyof CaseInput;
    (result[field] ??= []).push(problem.mensaje);
  }
  return result;
}
