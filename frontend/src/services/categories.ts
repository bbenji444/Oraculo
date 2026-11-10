/**
 * Servicio de subdivisiones (`/api/v1/categories`; docs/api.md, ADR-0038).
 *
 * Las categorías con que la IA clasifica cada nota por delito son también las
 * subdivisiones de la FGR. Cada una (menos «Otros») tiene un tema general: un
 * concepto con palabras clave para buscarla sola o junto con la FGR.
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2).
 *
 * No hace: las palabras clave del tema se editan con `services/concepts.ts`,
 * porque el tema es un concepto.
 */
import { apiUrl } from '../config/api';
import { ApiError, badFormat, requestJson } from './http';

export interface Category {
  id: number;
  name: string;
  /** Lo que debe entender la IA por ella. */
  description: string;
  /** «Otros»: a donde va lo que no encaja; no se apaga ni tiene tema. */
  is_other: boolean;
  /** #RRGGBB, o `null` si no tiene. */
  color: string | null;
  symbol: string | null;
  /** Si la IA la usa al clasificar. */
  is_active: boolean;
  /** Su tema general (un concepto de `/concepts`), si tiene. */
  topic_concept_id: number | null;
}

/** Lo que cambia de una subdivisión; lo que falta queda igual. */
export interface CategoryPatch {
  name?: string;
  description?: string;
  color?: string;
  is_active?: boolean;
}

function isCategory(value: unknown): value is Category {
  if (typeof value !== 'object' || value === null) return false;
  const c = value as Record<string, unknown>;
  return (
    typeof c.id === 'number' &&
    typeof c.name === 'string' &&
    typeof c.description === 'string' &&
    typeof c.is_other === 'boolean' &&
    typeof c.is_active === 'boolean' &&
    (c.topic_concept_id === null || typeof c.topic_concept_id === 'number')
  );
}

/**
 * Las subdivisiones en su orden, con «Otros» al final.
 *
 * @param includeInactive También las apagadas (el editor).
 * @param signal Señal para cancelar.
 * @returns Las subdivisiones.
 * @throws {ApiError} Si la API falla.
 */
export async function listCategories(
  includeInactive = false,
  signal?: AbortSignal,
): Promise<Category[]> {
  const query = includeInactive ? '?include_inactive=true' : '';
  const body = (await requestJson(`${apiUrl('categories')}${query}`, { signal })) as {
    items?: unknown;
  } | null;
  if (!Array.isArray(body?.items) || !body.items.every(isCategory)) throw badFormat();
  return body.items;
}

/**
 * Edita una subdivisión; su tema general toma el mismo nombre y estado.
 *
 * @param id Id de la subdivisión.
 * @param patch Lo que cambia.
 * @returns La subdivisión como quedó.
 * @throws {ApiError} `invalid_category`, `category_name_taken` o `category_not_found`.
 */
export async function updateCategory(id: number, patch: CategoryPatch): Promise<Category> {
  const body = await requestJson(apiUrl(`categories/${String(id)}`), {
    method: 'PATCH',
    body: patch,
  });
  if (!isCategory(body)) throw badFormat();
  return body;
}

/** Una subdivisión nueva con las palabras de su tema general (09/11/2026). */
export interface CategoryCreate {
  name: string;
  description: string;
  color: string;
  is_active: boolean;
  /** Palabras clave de su tema general; al menos una. */
  keywords: string[];
  exclude_terms: string[];
}

/**
 * Agrega una subdivisión antes de «Otros», con su tema general.
 *
 * @param data La subdivisión nueva.
 * @returns La subdivisión guardada.
 * @throws {ApiError} `invalid_category`, `invalid_concept` o `category_name_taken`.
 */
export async function createCategory(data: CategoryCreate): Promise<Category> {
  const body = await requestJson(apiUrl('categories'), { method: 'POST', body: data });
  if (!isCategory(body)) throw badFormat();
  return body;
}

/**
 * Borra una subdivisión: sus notas pasan a «Otros» y su tema general se retira.
 *
 * @param id Id de la subdivisión (nunca «Otros»).
 * @returns Cuántas notas pasaron a «Otros».
 * @throws {ApiError} `category_not_found` o `invalid_category` (si es «Otros»).
 */
export async function deleteCategory(id: number): Promise<number> {
  const body = (await requestJson(apiUrl(`categories/${String(id)}`), {
    method: 'DELETE',
  })) as { notes_moved_to_other?: unknown } | null;
  if (typeof body?.notes_moved_to_other !== 'number') throw badFormat();
  return body.notes_moved_to_other;
}

/** Problemas por campo de una subdivisión, como los entrega la API. */
export type CategoryFieldErrors = Partial<
  Record<keyof CategoryPatch | 'keywords' | 'exclude_terms', string[]>
>;

/**
 * Traduce un error de la API a mensajes por campo, para mostrarlos junto a
 * cada uno. Un nombre repetido (409) va en el campo nombre.
 *
 * @param error El error de la mutación.
 * @returns Los mensajes por campo; vacío si el error no es de validación.
 */
export function categoryFieldErrors(error: unknown): CategoryFieldErrors {
  if (!(error instanceof ApiError)) return {};
  if (error.code === 'category_name_taken') return { name: [error.message] };
  if (error.code !== 'invalid_category' && error.code !== 'invalid_concept') return {};
  const problems = error.details.problemas;
  const result: CategoryFieldErrors = {};
  if (!Array.isArray(problems)) return result;
  for (const problem of problems as { campo?: unknown; mensaje?: unknown }[]) {
    if (typeof problem.campo !== 'string' || typeof problem.mensaje !== 'string') continue;
    (result[problem.campo as keyof CategoryFieldErrors] ??= []).push(problem.mensaje);
  }
  return result;
}
