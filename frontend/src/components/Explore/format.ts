/**
 * Textos y cálculos de la pantalla Explorar, en español y sin tocar el DOM.
 *
 * Fechas siempre en hora de la Ciudad de México (CLAUDE.md §6.3), aunque el
 * navegador esté en otra zona.
 */
import type { Article, Precision, Search, SearchProgress } from '../../services/searches';

const MEXICO_CITY = 'America/Mexico_City';
const DATE_TIME = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const DATE_ONLY = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  day: 'numeric',
  month: 'short',
});

/**
 * Fecha y hora en la Ciudad de México.
 *
 * @example formatMexicoCity('2026-10-17T15:00:48Z') // '17/10/2026, 09:00'
 */
export function formatMexicoCity(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

/**
 * Día corto en la Ciudad de México.
 *
 * @example formatDay('2026-10-17T15:00:48Z') // '17 oct'
 */
export function formatDay(iso: string): string {
  return DATE_ONLY.format(new Date(iso)).replace('.', '');
}

/** Insignia de precisión de una ubicación (§14.4). */
export const PRECISION_LABEL: Record<Precision, string> = {
  country: 'País',
  state: 'Estado',
  municipality: 'Municipio',
  locality: 'Localidad',
  unknown: 'Sin ubicación',
};

/** Las ubicadas solo por estado o país se dibujan distinto (§14.2). */
export function isCoarse(precision: Precision): boolean {
  return precision === 'country' || precision === 'state';
}

// Etapas del pipeline en orden (backend: app/domain/search.py) y su texto.
const STAGES = ['plan', 'query', 'dedupe', 'extract', 'enrich', 'geocode', 'filter', 'close'];
const STAGE_LABEL: Record<string, string> = {
  plan: 'Planeando consultas',
  query: 'Consultando proveedores',
  dedupe: 'Quitando duplicados',
  extract: 'Leyendo el texto de las notas',
  enrich: 'Resumiendo y clasificando con la IA',
  geocode: 'Ubicando en el mapa',
  filter: 'Revisando qué cae en la región',
  close: 'Cerrando la búsqueda',
};
const PERCENT = 100;

/** Avance para la barra: etapa y porcentaje. */
export interface StageProgress {
  label: string;
  percent: number;
}

/**
 * Cuánto lleva una búsqueda. Cada etapa vale lo mismo; dentro de "resumir"
 * (la más larga) avanza según las notas ya resumidas.
 *
 * @example stageProgress({ stage: 'enrich', articles: 20, enriched: 10 }, 'running')
 * // { label: 'Resumiendo y clasificando con la IA', percent: 56 }
 */
export function stageProgress(progress: SearchProgress, status: Search['status']): StageProgress {
  if (status === 'completed' || status === 'partial')
    return { label: 'Terminada', percent: PERCENT };
  if (status === 'failed') return { label: 'No se pudo completar', percent: PERCENT };
  const stage = progress.stage ?? 'plan';
  const index = Math.max(0, STAGES.indexOf(stage));
  let within = 0;
  if (stage === 'enrich' && progress.articles) {
    const pending = progress.articles - (progress.reused ?? 0);
    within = pending > 0 ? Math.min(1, (progress.enriched ?? 0) / pending) : 1;
  }
  return {
    label: status === 'pending' ? 'En cola' : (STAGE_LABEL[stage] ?? stage),
    percent: Math.round(((index + within) / STAGES.length) * PERCENT),
  };
}

/**
 * Dólares con 4 decimales (los costos de IA son de centésimas de centavo).
 *
 * @example formatUsd(0.0129) // '0.0129 USD'
 */
export function formatUsd(value: number): string {
  return `${value.toFixed(4)} USD`;
}

/**
 * Notas que se ven en la lista y en el globo: por defecto solo las relevantes
 * para algún concepto. Las dos vistas usan esta misma función para que nunca
 * muestren cosas distintas (antes el globo pintaba también las descartadas).
 *
 * @param articles Todas las notas de la búsqueda.
 * @param showIrrelevant Si el interruptor "No relevantes" está prendido.
 * @returns Las notas a mostrar, en el mismo orden.
 * @example visibleArticles(notas, false) // solo las relevantes
 */
export function visibleArticles(articles: readonly Article[], showIrrelevant: boolean): Article[] {
  if (showIrrelevant) return [...articles];
  return articles.filter((article) => article.concepts.some((c) => c.is_relevant));
}
