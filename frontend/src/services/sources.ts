/**
 * Servicio de fuentes de la búsqueda manual (`GET /api/v1/sources`, F12.2,
 * ADR-0027): qué fuentes hay, cuáles cuestan créditos, cuáles están
 * configuradas y cuáles van encendidas por defecto.
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2).
 * `chosenSources` es lógica pura: con qué fuentes se busca según lo que el
 * analista encendió.
 */
import { apiUrl } from '../config/api';
import { badFormat, requestJson } from './http';

/** Un switch de fuente. */
export interface SourceOption {
  /** Valor para `providers` (`google_news_rss`, `indice_local`, `searchapi`…). */
  id: string;
  label: string;
  /** Si gasta créditos (SearchApi) o es gratis. */
  paid: boolean;
  /** Sin configurar, el switch se ve apagado y no se puede encender. */
  configured: boolean;
  default_on: boolean;
}

function isSourceOption(value: unknown): value is SourceOption {
  if (typeof value !== 'object' || value === null) return false;
  const s = value as Record<string, unknown>;
  return (
    typeof s.id === 'string' &&
    typeof s.label === 'string' &&
    typeof s.paid === 'boolean' &&
    typeof s.configured === 'boolean' &&
    typeof s.default_on === 'boolean'
  );
}

/**
 * Las fuentes en el orden de pantalla.
 *
 * @param signal Señal para cancelar.
 */
export async function fetchSources(signal?: AbortSignal): Promise<SourceOption[]> {
  const body = (await requestJson(apiUrl('sources'), { signal })) as { items?: unknown } | null;
  if (!Array.isArray(body?.items) || !body.items.every(isSourceOption)) throw badFormat();
  return body.items;
}

/**
 * Fuentes con las que se busca: lo que encendió el analista (o, si todavía
 * no ha tocado nada, las de por defecto), solo entre las configuradas.
 *
 * @param options Fuentes de la API.
 * @param chosen Las que encendió el analista, o `null` si no ha elegido.
 * @returns Los `id`, en el orden de pantalla.
 * @example
 * chosenSources(options, null) // las default_on configuradas
 * chosenSources(options, ['searchapi']) // ['searchapi'] si está configurada
 */
export function chosenSources(
  options: readonly SourceOption[],
  chosen: readonly string[] | null,
): string[] {
  return options
    .filter((o) => o.configured && (chosen === null ? o.default_on : chosen.includes(o.id)))
    .map((o) => o.id);
}
