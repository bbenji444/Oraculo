/**
 * Servicio del índice local (`/api/v1/local-index`): pestaña temporal "Notas".
 *
 * Permite ver desde ya las notas que junta la ingesta (ADR-0014). La Fase 6
 * la reemplaza por el globo con resultados. Los componentes nunca llaman a
 * fetch directamente (CLAUDE.md §6.2).
 */
import { apiUrl } from '../config/api';
import { badFormat, requestJson } from './http';

/** Una nota del índice: metadatos y link, nunca el artículo. */
export interface IndexNote {
  title: string;
  url: string;
  source_domain: string | null;
  published_at: string | null;
  snippet: string | null;
  /** gdelt_ngrams, gdelt_gkg o rss:<medio>. */
  source: string;
  gdelt_states: string[];
}

export interface Count {
  label: string;
  count: number;
}

export interface LocalIndexSearch {
  concept_name: string;
  region: string;
  period: string;
  query_text: string;
  status: 'ok' | 'skipped' | 'error';
  message: string | null;
  total: number;
  notes: IndexNote[];
  by_day: Count[];
  by_source: Count[];
}

export interface SourceStats {
  source: string;
  notes: number;
  with_body: number;
  body_mb: number;
  oldest: string | null;
  newest: string | null;
}

export interface IndexStats {
  sources: SourceStats[];
  total_notes: number;
  total_mb: number;
  last_run_at: string | null;
}

/**
 * Busca un concepto guardado en el índice local.
 *
 * @param args Concepto, región y días.
 * @returns Las notas encontradas y sus conteos.
 */
export async function searchLocalIndex(args: {
  conceptId: number;
  regionId: number;
  days: number;
}): Promise<LocalIndexSearch> {
  const params = new URLSearchParams({
    concept_id: String(args.conceptId),
    region_id: String(args.regionId),
    days: String(args.days),
  });
  const body = (await requestJson(
    `${apiUrl('local-index/search')}?${params.toString()}`,
  )) as LocalIndexSearch | null;
  if (!body || !Array.isArray(body.notes)) throw badFormat();
  return body;
}

/**
 * Resumen del índice: notas por fuente, espacio y última corrida.
 *
 * @param signal Para cancelar la petición.
 * @returns El resumen.
 */
export async function getIndexStats(signal?: AbortSignal): Promise<IndexStats> {
  const body = (await requestJson(apiUrl('local-index/stats'), { signal })) as IndexStats | null;
  if (!body || !Array.isArray(body.sources)) throw badFormat();
  return body;
}

/** Nombre legible de cada fuente del índice. */
export const SOURCE_LABEL: Record<string, string> = {
  gdelt_ngrams: 'GDELT (texto completo)',
  gdelt_gkg: 'GDELT (títulos)',
};

/**
 * Nombre para mostrar de una fuente (los RSS llegan como `rss:<medio>`).
 *
 * @param source Fuente tal como la guarda el índice.
 * @returns Nombre legible.
 */
export function sourceLabel(source: string): string {
  if (source.startsWith('rss:')) return `RSS · ${source.slice('rss:'.length)}`;
  return SOURCE_LABEL[source] ?? source;
}
