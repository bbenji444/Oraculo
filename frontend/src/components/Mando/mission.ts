/**
 * Lógica pura del diseño «Centro de mando» (diseño 3, 27/10/2026): la frase
 * de la consulta, la hora de la próxima corrida automática, las consultas
 * recientes y la bitácora del barrido.
 *
 * Benji pidió una búsqueda «muy personalizada» que se sienta de un sistema
 * de millones: en lugar de un formulario, la búsqueda se lee como una orden
 * («Rastrear FGR en Jalisco durante los últimos 7 días vía 2 fuentes») y
 * cada parte se toca para cambiarla.
 *
 * No hace: no dibuja ni pide datos; recibe lo que ya trajeron los hooks.
 */
import type { DateRange, ListFilter } from '../../store/explorer';
import { isFinished, type Search } from '../../services/searches';
import type { SourceOption } from '../../services/sources';
import { formatRange, STAGE_LABEL, STAGES } from '../Explore/format';

/**
 * Parámetro de la URL que vuelve al diseño 2 (la columna a la izquierda):
 * `?clasico#/explorar`. Desde el 27/10/2026 el Centro de mando es el diseño
 * principal; el anterior se guarda por si se ocupa (Benji).
 */
export const CLASSIC_PARAM = 'clasico';

/**
 * Si se ve el diseño «Centro de mando» (el principal) y no el de columna.
 *
 * @param search La parte `?…` de la URL (por defecto, la de la ventana).
 */
export function isMandoMode(search: string = window.location.search): boolean {
  return !new URLSearchParams(search).has(CLASSIC_PARAM);
}

// Palabras que no entran en una sigla («Fiscalía General de la República» → FGR).
const SIGLA_SKIP = new Set(['de', 'del', 'la', 'las', 'los', 'el', 'en', 'y', 'e', 'o', 'a']);
// A partir de este largo, un concepto se muestra con su sigla en las fichas cortas.
const SHORT_NAME_MAX = 18;

/**
 * Nombre corto de un concepto, para las fichas de consultas recientes.
 *
 * @example shortConcept('Fiscalía General de la República') // 'FGR'
 * @example shortConcept('Extorsión') // 'Extorsión'
 */
export function shortConcept(name: string): string {
  if (name.length <= SHORT_NAME_MAX) return name;
  const words = name.split(/\s+/).filter((word) => word && !SIGLA_SKIP.has(word.toLowerCase()));
  if (words.length < 2) return name;
  return words.map((word) => word.charAt(0).toUpperCase()).join('');
}

/**
 * Los conceptos elegidos, como se leen en la frase.
 *
 * @example conceptsLabel(['Extorsión', 'Robo']) // 'Extorsión y Robo'
 * @example conceptsLabel(['A', 'B', 'C']) // 'A y 2 más'
 */
export function conceptsLabel(names: readonly string[]): string {
  if (names.length === 0) return 'elige un concepto';
  if (names.length === 1) return names[0] ?? '';
  if (names.length === 2) return `${names[0] ?? ''} y ${names[1] ?? ''}`;
  return `${names[0] ?? ''} y ${String(names.length - 1)} más`;
}

// Con más subdivisiones que estas, la frase dice cuántas en lugar de nombrarlas.
const SUBDIVISIONS_NAMED = 2;

/**
 * Las subdivisiones elegidas, como se leen junto a la FGR.
 *
 * @example subdivisionsLabel(['Homicidio']) // 'Homicidio'
 * @example subdivisionsLabel(['Homicidio', 'Secuestro', 'Extorsión']) // '3 subdivisiones'
 */
export function subdivisionsLabel(names: readonly string[]): string {
  if (names.length <= SUBDIVISIONS_NAMED) return names.join(' y ');
  return `${String(names.length)} subdivisiones`;
}

/**
 * Lo que se va a rastrear, un nombre por concepto elegido. A la FGR (un
 * concepto que no es tema general) se le pegan sus subdivisiones: «FGR ·
 * Homicidio» (ADR-0038).
 *
 * @param chosen Conceptos elegidos, en orden.
 * @param subdivisionNames Nombres de las subdivisiones elegidas.
 * @example trackNames([{ name: 'Fiscalía General de la República', category_id: null }], ['Homicidio'])
 * // ['FGR · Homicidio']
 */
export function trackNames(
  chosen: readonly { name: string; category_id: number | null }[],
  subdivisionNames: readonly string[],
): string[] {
  return chosen.map((concept) =>
    concept.category_id === null && subdivisionNames.length > 0
      ? `${shortConcept(concept.name)} · ${subdivisionsLabel(subdivisionNames)}`
      : concept.name,
  );
}

/**
 * El rango de fechas, como se lee en la frase.
 *
 * @example rangeLabel({ kind: '7' }) // 'los últimos 7 días'
 */
export function rangeLabel(range: DateRange): string {
  if (range.kind === 'today') return 'hoy';
  if (range.kind === '7') return 'los últimos 7 días';
  if (range.kind === '30') return 'los últimos 30 días';
  if (range.from && range.to) return formatRange(range.from, range.to);
  return 'fechas por elegir';
}

/**
 * La palabra que va antes del rango en la frase: «Rastrear … hoy», «… durante
 * los últimos 7 días», «… en el periodo 10 – 17 oct 2026».
 */
export function rangeConnector(range: DateRange): string {
  if (range.kind === 'today') return '';
  if (range.kind === 'custom') return 'en el periodo';
  return 'durante';
}

/**
 * Las fuentes encendidas, como se leen en la frase.
 *
 * @param options Todas las fuentes del servidor.
 * @param chosen `id` de las encendidas.
 * @example sourcesLabel(opciones, ['google_news_rss', 'indice_local']) // '2 fuentes gratis'
 */
export function sourcesLabel(options: readonly SourceOption[], chosen: readonly string[]): string {
  if (chosen.length === 0) return 'ninguna fuente';
  const paid = options.filter((o) => o.paid && chosen.includes(o.id)).length;
  const noun = chosen.length === 1 ? 'fuente' : 'fuentes';
  if (paid === 0) return `${String(chosen.length)} ${noun} gratis`;
  return `${String(chosen.length)} ${noun} · ${String(paid)} de pago`;
}

// Horas iniciales de las corridas automáticas (ADR-0031). Solo se usan mientras
// no llega el horario único del servidor (`/schedule`, ADR-0040).
export const AUTOMATIC_RUN_HOURS = [7, 15, 23] as const;
const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR;
const MEXICO_CITY = 'America/Mexico_City';

const MEXICO_PARTS = new Intl.DateTimeFormat('en-US', {
  timeZone: MEXICO_CITY,
  hourCycle: 'h23',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

/** Hora, minuto y segundo en la Ciudad de México. */
function mexicoClock(now: Date): { hour: number; minute: number; second: number } {
  const parts = MEXICO_PARTS.formatToParts(now);
  const part = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return { hour: part('hour'), minute: part('minute'), second: part('second') };
}

const MS_PER_SECOND = 1000;
const pad = (n: number) => String(n).padStart(2, '0');

/**
 * La próxima corrida automática y cuánto falta.
 *
 * @param now Momento actual.
 * @param upcoming Próximas corridas del horario único (ISO, de `/schedule`).
 *   Sin ellas se usan las horas iniciales (7, 15 y 23).
 * @returns La hora «HH:MM» de la Ciudad de México y los segundos que faltan.
 * @example nextAutomaticRun(new Date('2026-10-27T19:00:00Z')) // { time: '15:00', seconds: 7200 } (13:00 en CDMX)
 */
export function nextAutomaticRun(
  now: Date,
  upcoming: readonly string[] = [],
): { time: string; seconds: number } {
  const next = upcoming.map((iso) => new Date(iso)).find((at) => at.getTime() > now.getTime());
  if (next) {
    const { hour, minute } = mexicoClock(next);
    return {
      time: `${pad(hour)}:${pad(minute)}`,
      seconds: Math.round((next.getTime() - now.getTime()) / MS_PER_SECOND),
    };
  }
  const { hour, minute, second } = mexicoClock(now);
  const elapsed = hour * SECONDS_PER_HOUR + minute * 60 + second;
  for (const runHour of AUTOMATIC_RUN_HOURS) {
    const at = runHour * SECONDS_PER_HOUR;
    if (at > elapsed) return { time: `${pad(runHour)}:00`, seconds: at - elapsed };
  }
  const first = AUTOMATIC_RUN_HOURS[0];
  return {
    time: `${pad(first)}:00`,
    seconds: SECONDS_PER_DAY - elapsed + first * SECONDS_PER_HOUR,
  };
}

/**
 * Cuánto falta, en corto.
 *
 * @example countdownLabel(6120) // '1 h 42 min'
 * @example countdownLabel(45) // 'menos de 1 min'
 */
export function countdownLabel(seconds: number): string {
  const hours = Math.floor(seconds / SECONDS_PER_HOUR);
  const minutes = Math.floor((seconds % SECONDS_PER_HOUR) / 60);
  if (hours === 0 && minutes === 0) return 'menos de 1 min';
  if (hours === 0) return `${String(minutes)} min`;
  return `${String(hours)} h ${String(minutes).padStart(2, '0')} min`;
}

const CLOCK = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  hourCycle: 'h23',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

const RUN_CLOCK = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  hourCycle: 'h23',
  hour: '2-digit',
  minute: '2-digit',
});

const SHORT_DAY = new Intl.DateTimeFormat('es-MX', {
  timeZone: MEXICO_CITY,
  day: 'numeric',
  month: 'short',
});

function shortDay(iso: string): string {
  return SHORT_DAY.format(new Date(iso)).replace('.', '');
}

/**
 * Las horas que cubre una corrida automática, en corto: «23:00 – 07:00».
 *
 * @returns El texto, o `null` si la búsqueda no tiene ventana por horas
 *   (las manuales y las corridas de antes del 28/10/2026).
 */
export function windowHours(search: Pick<Search, 'window_start' | 'window_end'>): string | null {
  if (!search.window_start || !search.window_end) return null;
  return `${RUN_CLOCK.format(new Date(search.window_start))} – ${RUN_CLOCK.format(
    new Date(search.window_end),
  )}`;
}

/**
 * Las horas que cubre una corrida, con su día: «27 oct 23:00 – 28 oct 07:00»
 * o «28 oct, 07:00 – 15:00» si es el mismo día.
 */
export function windowLabel(search: Pick<Search, 'window_start' | 'window_end'>): string | null {
  if (!search.window_start || !search.window_end) return null;
  const from = shortDay(search.window_start);
  const to = shortDay(search.window_end);
  const startHour = RUN_CLOCK.format(new Date(search.window_start));
  const endHour = RUN_CLOCK.format(new Date(search.window_end));
  return from === to
    ? `${to}, ${startHour} – ${endHour}`
    : `${from} ${startHour} – ${to} ${endHour}`;
}

/**
 * Ficha de una corrida automática: «Corrida de las 07:00 · 23:00 – 07:00».
 * Las de antes de la ventana por horas dicen cuántas notas trajeron.
 */
export function runLabel(
  search: Pick<Search, 'scheduled_for' | 'results_count' | 'window_start' | 'window_end'>,
): string {
  const hour = search.scheduled_for
    ? ` de las ${RUN_CLOCK.format(new Date(search.scheduled_for))}`
    : '';
  const hours = windowHours(search);
  return `Corrida${hour} · ${hours ?? `${String(search.results_count)} notas`}`;
}

/**
 * Ficha de una búsqueda manual anterior: «Tu búsqueda del 27 oct: FGR en Jalisco».
 */
export function recentLabel(
  search: Pick<Search, 'concepts' | 'region_name' | 'created_at'>,
): string {
  // El primer concepto completo («Balacera en Iztapalapa y 2 más»); las siglas
  // de varios juntos no se entendían («BI + Balacera + JBOH»).
  const names = search.concepts.map((c) => c.name);
  const what = names.length === 1 ? shortConcept(names[0] ?? '') : conceptsLabel(names);
  return `Tu búsqueda del ${shortDay(search.created_at)}: ${what} en ${search.region_name}`;
}

/** Reloj de la Ciudad de México: «13:42:05». */
export function clockLabel(now: Date): string {
  return CLOCK.format(now);
}

/**
 * Tiempo transcurrido, como cronómetro.
 *
 * @example elapsedLabel('2026-10-27T19:00:00Z', new Date('2026-10-27T19:01:05Z')) // '01:05'
 */
export function elapsedLabel(startIso: string | null, now: Date): string {
  if (!startIso) return '00:00';
  const seconds = Math.max(0, Math.floor((now.getTime() - Date.parse(startIso)) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

const DAY_MS = 86_400_000;

/** Días que cubre una búsqueda, contando el primero y el último. */
export function spanDays(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / DAY_MS) + 1;
}

/**
 * Ficha corta de una búsqueda: «FGR · Jalisco · 7 días».
 */
export function missionLabel(
  search: Pick<
    Search,
    'concepts' | 'region_name' | 'date_from' | 'date_to' | 'window_start' | 'window_end'
  >,
): string {
  const concepts = search.concepts.map((c) => shortConcept(c.name)).join(' + ');
  // Corridas automáticas: sus horas, no los días que tocan.
  const hours = windowHours(search);
  if (hours) return `${concepts} · ${search.region_name} · ${hours}`;
  const days = spanDays(search.date_from, search.date_to);
  return `${concepts} · ${search.region_name} · ${String(days)} ${days === 1 ? 'día' : 'días'}`;
}

// Cuántas consultas recientes caben en la consola sin saturarla.
export const RECENT_MISSIONS = 3;

/**
 * Las últimas búsquedas manuales distintas que dieron notas, para repetirlas
 * con un clic. Dos búsquedas con la misma región, conceptos y duración
 * cuentan como una sola (la más nueva).
 *
 * @param history Historial, de la más nueva a la más vieja.
 * @param limit Cuántas devolver.
 */
export function recentMissions(history: readonly Search[], limit = RECENT_MISSIONS): Search[] {
  const seen = new Set<string>();
  const result: Search[] = [];
  for (const search of history) {
    if (search.trigger === 'automatic') continue;
    if (search.status === 'failed' || !isFinished(search.status)) continue;
    if (search.results_count === 0) continue;
    const key = [
      search.region_id,
      search.concepts
        .map((c) => c.id)
        .sort((a, b) => a - b)
        .join(','),
      spanDays(search.date_from, search.date_to),
    ].join('|');
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(search);
    if (result.length === limit) break;
  }
  return result;
}

/** Nombre corto de cada etapa, para los nodos del riel de avance. */
export const STAGE_SHORT: Readonly<Record<string, string>> = {
  plan: 'Plan',
  query: 'Fuentes',
  dedupe: 'Duplicados',
  extract: 'Lectura',
  enrich: 'IA',
  // «Mapa» y «Región» se confundían (Benji, 10/11/2026): una ubica cada nota
  // y la otra decide si cae dentro de la zona buscada.
  geocode: 'Ubicar',
  filter: 'Zona',
  close: 'Cierre',
};

/**
 * En qué etapa va el barrido: su posición en `STAGES`, o `STAGES.length` si
 * ya terminó.
 */
export function stageIndex(search: Pick<Search, 'status' | 'progress'>): number {
  if (isFinished(search.status)) return STAGES.length;
  if (search.status === 'pending') return 0;
  return Math.max(0, STAGES.indexOf(search.progress.stage ?? 'plan'));
}

/**
 * Bitácora del barrido: un renglón por etapa alcanzada, con los números que
 * ya se conocen. La última línea es la etapa en curso.
 *
 * @example missionLog(busqueda) // ['Plan: 4 consultas', 'Notas encontradas: 102 (la IA decide cuáles sirven)', …]
 */
export function missionLog(
  search: Pick<Search, 'status' | 'progress' | 'queries_planned' | 'results_count'>,
): string[] {
  const reached = stageIndex(search);
  const { progress } = search;
  const lines: string[] = [];
  const at = (stage: string) => STAGES.indexOf(stage) <= reached;
  if (search.status === 'pending') return ['En cola: el barrido arranca en un momento'];
  if (at('plan')) lines.push(`Plan: ${String(search.queries_planned)} consultas`);
  if (at('query')) {
    lines.push(
      progress.articles !== undefined && STAGES.indexOf('query') < reached
        ? // Son las que se van a revisar, no los resultados: Benji pensó que
          // «Fuentes consultadas: 512 notas» eran 512 resultados (28/10/2026).
          `Notas encontradas: ${String(progress.articles)} (la IA decide cuáles sirven)`
        : 'Consultando fuentes…',
    );
  }
  if (at('extract')) lines.push(STAGE_LABEL.extract ?? 'Leyendo notas');
  if (at('enrich')) {
    const pending = (progress.articles ?? 0) - (progress.reused ?? 0);
    const reused = progress.reused ? ` · ${String(progress.reused)} ya leídas antes` : '';
    lines.push(
      `IA leyendo: ${String(progress.enriched ?? 0)} de ${String(Math.max(0, pending))} nuevas${reused}`,
    );
  }
  if (at('geocode')) lines.push(STAGE_LABEL.geocode ?? 'Ubicando');
  if (at('filter') && progress.in_region !== undefined) {
    lines.push(
      `${String(progress.in_region)} dentro · ${String(progress.out_of_region ?? 0)} fuera · ${String(
        progress.unlocated ?? 0,
      )} sin ubicar`,
    );
  }
  if (isFinished(search.status)) {
    lines.push(
      search.status === 'failed'
        ? 'Barrido interrumpido'
        : `Barrido completo: ${String(search.results_count)} notas`,
    );
  }
  return lines;
}

/** Cuántos filtros hay puestos, para el número del botón. */
export function activeFilters(
  categoryIds: readonly number[],
  stateCode: string | null,
  listFilter: ListFilter,
  showIrrelevant: boolean,
): number {
  return (
    categoryIds.length +
    (stateCode === null ? 0 : 1) +
    (listFilter === 'all' ? 0 : 1) +
    (showIrrelevant ? 1 : 0)
  );
}
