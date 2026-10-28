/**
 * Textos y cálculos de la pantalla Explorar, en español y sin tocar el DOM.
 *
 * Fechas siempre en hora de la Ciudad de México (CLAUDE.md §6.3), aunque el
 * navegador esté en otra zona.
 */
import type {
  Article,
  Authority,
  Precision,
  Search,
  SearchProgress,
} from '../../services/searches';
import { isFinished } from '../../services/searches';

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
export const STAGES = [
  'plan',
  'query',
  'dedupe',
  'extract',
  'enrich',
  'geocode',
  'filter',
  'close',
];
export const STAGE_LABEL: Record<string, string> = {
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

/** Encabezado de la lista de noticias y su ayuda (ver `newsCount`). */
export interface NewsCount {
  label: string;
  hint: string;
}

// Las descargas (PDF, CSV, GeoJSON) solo llevan notas relevantes (ADR-0018).
const DOWNLOADS_NOTE = 'Las descargas incluyen solo las relevantes.';

/**
 * Encabezado de la lista: cuántas notas se ven y cuántas tiene la búsqueda.
 *
 * Arriba dice "43 notas" (todas las que trajo la búsqueda) y la lista muestra
 * solo las relevantes; sin este "24 de 43" parecía que faltaban notas.
 *
 * @param shown Notas en la lista (las relevantes, o todas con "No relevantes").
 * @param total Notas de la búsqueda.
 * @returns El texto del encabezado y la ayuda que explica las ocultas.
 * @example newsCount(24, 43).label // "Noticias (24 de 43)"
 */
export function newsCount(shown: number, total: number): NewsCount {
  const hidden = total - shown;
  if (hidden <= 0) {
    return {
      label: `Noticias (${String(total)})`,
      hint: 'Las descargas incluyen solo las notas relevantes.',
    };
  }
  const noun = hidden === 1 ? 'no relevante oculta' : 'no relevantes ocultas';
  return {
    label: `Noticias (${String(shown)} de ${String(total)})`,
    hint: `${String(hidden)} ${noun}: actívalas con «No relevantes». ${DOWNLOADS_NOTE}`,
  };
}

// Meses cortos en español para formatRange (sin depender del idioma del equipo).
const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/**
 * Periodo de una búsqueda en corto, para el renglón compacto del panel.
 *
 * @param from Primer día (AAAA-MM-DD).
 * @param to Último día (AAAA-MM-DD).
 * @returns "10 – 17 oct 2026", o "28 sep – 5 oct 2026" si cambia el mes.
 * @example formatRange('2026-10-10', '2026-10-17') // '10 – 17 oct 2026'
 */
export function formatRange(from: string, to: string): string {
  const [fromYear, fromMonth, fromDay] = from.split('-').map(Number);
  const [toYear, toMonth, toDay] = to.split('-').map(Number);
  const month = (m: number | undefined) => MONTHS[(m ?? 1) - 1] ?? '';
  const start =
    fromMonth === toMonth && fromYear === toYear
      ? String(fromDay)
      : `${String(fromDay)} ${month(fromMonth)}${fromYear === toYear ? '' : ` ${String(fromYear)}`}`;
  return `${start} – ${String(toDay)} ${month(toMonth)} ${String(toYear)}`;
}

export interface FinishNotice {
  tone: 'ok' | 'warn' | 'error';
  text: string;
}

/**
 * Aviso de que una búsqueda terminó, para quien se fue a otra pestaña o dejó
 * de mirar la barra de avance. `partial` es que algún proveedor falló pero hay
 * notas (§9 paso 8).
 *
 * @example finishNotice({ status: 'completed', results_count: 18 }) // 'Búsqueda lista: 18 notas'
 */
export function finishNotice(search: Pick<Search, 'status' | 'results_count'>): FinishNotice {
  const notes = `${String(search.results_count)} ${search.results_count === 1 ? 'nota' : 'notas'}`;
  if (search.status === 'failed') return { tone: 'error', text: 'La búsqueda falló' };
  if (search.status === 'partial')
    return { tone: 'warn', text: `Búsqueda lista con avisos: ${notes}` };
  return { tone: 'ok', text: `Búsqueda lista: ${notes}` };
}

// Diferencia mínima entre el hecho y la publicación para avisarlo: con menos,
// es la misma noticia del día ("ayer", "el lunes").
const OLD_EVENT_DAYS = 3;
const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Fecha del hecho para la ficha, solo si es distinta de la publicación.
 *
 * Muchas notas son avances de casos viejos (una orden de captura por un
 * homicidio de hace un año, historial del 20/10/2026): sin esto parecía un
 * hecho reciente.
 *
 * Dice «se refiere a hechos del…» y no «el hecho ocurrió el…»: la IA suele
 * dar la fecha de los antecedentes, no la del suceso que cuenta la nota. En
 * la corrida del 26/10/2026, la vinculación a proceso de Jáuregui del 25/10
 * salió con fechas de abril (el operativo) en 57 de 111 notas con fecha.
 *
 * @param eventDate Fecha del hecho según la IA (AAAA-MM-DD), si hay.
 * @param publishedAt Publicación (ISO, UTC), si hay.
 * @returns "Se refiere a hechos del 29 sep 2025", o `null` si no aplica.
 * @example eventDateNote('2025-09-29', '2026-10-16T14:00:00Z') // 'Se refiere a hechos del 29 sep 2025'
 */
export function eventDateNote(eventDate: string | null, publishedAt: string | null): string | null {
  if (!eventDate || !publishedAt) return null;
  const [year, month, day] = eventDate.split('-').map(Number);
  if (!year || !month || !day) return null;
  const gap = Math.abs(Date.parse(publishedAt) - Date.UTC(year, month - 1, day));
  if (!Number.isFinite(gap) || gap < OLD_EVENT_DAYS * DAY_MS) return null;
  return `Se refiere a hechos del ${String(day)} ${MONTHS[month - 1] ?? ''} ${String(year)}`;
}

const RUN_HOUR = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

/**
 * Rótulo de una corrida del monitor automático FGR (F12.8, ADR-0031).
 *
 * @example automaticRunLabel({ trigger: 'automatic', scheduled_for: '2026-10-26T05:00:00Z' })
 * // 'Monitor automático · corrida de las 23:00 del 25 oct'
 * @returns El rótulo, o `null` si la pidió una persona.
 */
export function automaticRunLabel(
  search: Pick<Search, 'trigger' | 'scheduled_for'>,
): string | null {
  if (search.trigger !== 'automatic') {
    return null;
  }
  if (!search.scheduled_for) {
    return 'Monitor automático';
  }
  const hour = RUN_HOUR.format(new Date(search.scheduled_for));
  return `Monitor automático · corrida de las ${hour} del ${formatDay(search.scheduled_for)}`;
}

/**
 * La corrida automática terminada más reciente (F12.8), para el acceso directo
 * de Explorar. El historial viene de la más nueva a la más vieja.
 */
export function latestRun(searches: readonly Search[]): Search | undefined {
  return searches.find((s) => s.trigger === 'automatic' && isFinished(s.status));
}

/** Quién actúa en la nota, en palabras (F12.5, ADR-0030). */
export const AUTHORITY_LABEL: Readonly<Record<Authority, string>> = {
  fgr: 'FGR federal',
  fgr_mencion: 'FGR solo mencionada',
  estatal: 'Fiscalía estatal',
  otra: 'Otra autoridad',
  sin_dato: 'No se sabe',
};

/**
 * Renglón «Quién actúa» de la ficha.
 *
 * @param authority Lo que dijo la IA, o `null`/ausente si falta clasificar.
 * @returns «Quién actúa: Fiscalía estatal», o `null` si no hay dato que mostrar.
 */
export function authorityNote(authority: Authority | null | undefined): string | null {
  if (!authority || authority === 'sin_dato') {
    return null;
  }
  return `Quién actúa: ${AUTHORITY_LABEL[authority]}`;
}

/**
 * Nombre corto de cada fuente, para la fila de la lista, la ficha y el
 * historial (F12.2). Coincide con los switches del panel de búsqueda.
 */
export const PROVIDER_LABEL: Readonly<Record<string, string>> = {
  google_news_rss: 'Google News RSS',
  indice_local: 'Índice local',
  searchapi: 'SearchApi',
  gdelt: 'GDELT',
  browserwork_bing: 'Bing',
  browserwork_google2: 'Google 2',
};

/**
 * Fuentes en texto: «Google News RSS · Índice local».
 *
 * @param providers `id` de las fuentes (`search_results.provider` o `searches.providers`).
 * @returns Los nombres separados por « · »; un `id` desconocido se muestra tal cual.
 */
export function providersLabel(providers: readonly string[]): string {
  return providers.map((p) => PROVIDER_LABEL[p] ?? p).join(' · ');
}

/**
 * Si una nota entra en el filtro de ubicación: todas, dentro de la región,
 * fuera o sin ubicación (§9 paso 7). Lo usan la lista y el filtro del
 * expediente del Centro de mando.
 *
 * @example matchesListFilter(nota, 'false') // true si cayó fuera de la región
 */
export function matchesListFilter(
  article: Pick<Article, 'in_region'>,
  filter: 'all' | 'true' | 'false' | 'none',
): boolean {
  if (filter === 'all') return true;
  if (filter === 'none') return article.in_region === null;
  return article.in_region === (filter === 'true');
}
