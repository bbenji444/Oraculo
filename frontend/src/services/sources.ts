/**
 * Servicio de fuentes de la búsqueda manual (`GET /api/v1/sources`, F12.2,
 * ADR-0027): qué fuentes hay, cuáles cuestan créditos, cuáles están
 * configuradas y cuáles van encendidas por defecto.
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2).
 * `chosenSources` es lógica pura: con qué fuentes se busca según lo que el
 * analista encendió.
 *
 * `credits_remaining` es opcional (ADR-0115): el servidor puede decir cuántos
 * créditos le quedan a la cuenta de SearchApi para pintarlo junto al switch.
 * Si no viene o no es un número, se descarta sin tumbar la lista.
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
  /** Si tarda más porque abre un navegador real (BrowserWork, ADR-0028). */
  slow?: boolean;
  /** Sin configurar, el switch se ve apagado y no se puede encender. */
  configured: boolean;
  default_on: boolean;
  /**
   * Si va encendida en la búsqueda rápida mientras el analista no toque los
   * switches (ADR-0115: ahí sí va Google web). Un servidor viejo no lo manda:
   * entonces vale lo mismo que `default_on`.
   */
  quick_default_on?: boolean;
  /**
   * Créditos que le quedan a la cuenta de la fuente (solo las de pago), si el
   * servidor los consultó. `null` o ausente: no se sabe y no se muestra.
   */
  credits_remaining?: number | null;
}

/** El número de créditos si es un conteo válido; si no, `null` (no se sabe). */
function creditsCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;
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
 * @returns Las fuentes, con `credits_remaining` en número o `null`.
 * @throws ApiError si la respuesta no tiene la forma esperada.
 */
export async function fetchSources(signal?: AbortSignal): Promise<SourceOption[]> {
  const body = (await requestJson(apiUrl('sources'), { signal })) as { items?: unknown } | null;
  if (!Array.isArray(body?.items) || !body.items.every(isSourceOption)) throw badFormat();
  // Un servidor viejo no manda el campo y uno nuevo podría mandarlo raro: en
  // los dos casos el switch sigue sirviendo, solo sin el número.
  return body.items.map((item) => {
    const quick: unknown = (item as { quick_default_on?: unknown }).quick_default_on;
    return {
      ...item,
      quick_default_on: typeof quick === 'boolean' ? quick : item.default_on,
      credits_remaining: creditsCount(item.credits_remaining),
    };
  });
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

/**
 * Fuentes de la búsqueda rápida mientras el analista no toque los switches:
 * las de `quick_default_on` (con Google web si hay créditos, ADR-0115), solo
 * entre las configuradas.
 *
 * @param options Fuentes de la API.
 * @returns Los `id`, en el orden de pantalla.
 * @example quickDefaultSources(options) // ['google_news_rss', 'indice_local', 'searchapi_web']
 */
export function quickDefaultSources(options: readonly SourceOption[]): string[] {
  return options
    .filter((o) => o.configured && (o.quick_default_on ?? o.default_on))
    .map((o) => o.id);
}
