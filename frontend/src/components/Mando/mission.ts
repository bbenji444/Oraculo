/**
 * Lógica pura del diseño «Centro de mando» (diseño 3, 27/10/2026): la frase
 * de la misión, la hora de la próxima corrida automática, las misiones
 * recientes y la bitácora del barrido.
 *
 * Benji pidió una búsqueda «muy personalizada» que se sienta de un sistema
 * de millones: en lugar de un formulario, la búsqueda se lee como una orden
 * («Rastrear FGR en Jalisco durante los últimos 7 días vía 2 fuentes») y
 * cada parte se toca para cambiarla.
 *
 * No hace: no dibuja ni pide datos; recibe lo que ya trajeron los hooks.
 */
import type { DateRange } from '../../store/explorer';
import { isFinished, type Search } from '../../services/searches';
import type { SourceOption } from '../../services/sources';
import { formatRange, STAGE_LABEL, STAGES } from '../Explore/format';

/** Parámetro de la URL que enciende el diseño: `?mando#/explorar`. */
export const MANDO_PARAM = 'mando';

/**
 * Si el diseño «Centro de mando» está encendido.
 *
 * @param search La parte `?…` de la URL (por defecto, la de la ventana).
 */
export function isMandoMode(search: string = window.location.search): boolean {
  return new URLSearchParams(search).has(MANDO_PARAM);
}

// Palabras que no entran en una sigla («Fiscalía General de la República» → FGR).
const SIGLA_SKIP = new Set(['de', 'del', 'la', 'las', 'los', 'el', 'en', 'y', 'e', 'o', 'a']);
// A partir de este largo, un concepto se muestra con su sigla en las fichas cortas.
const SHORT_NAME_MAX = 18;

/**
 * Nombre corto de un concepto, para las fichas de misiones recientes.
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

// Horas de las corridas automáticas del monitor FGR, en la Ciudad de México (ADR-0031).
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

/**
 * La próxima corrida automática y cuánto falta.
 *
 * @param now Momento actual.
 * @returns La hora (7, 15 o 23) y los segundos que faltan.
 * @example nextAutomaticRun(new Date('2026-10-27T19:00:00Z')) // { hour: 15, seconds: 7200 } (13:00 en CDMX)
 */
export function nextAutomaticRun(now: Date): { hour: number; seconds: number } {
  const { hour, minute, second } = mexicoClock(now);
  const elapsed = hour * SECONDS_PER_HOUR + minute * 60 + second;
  for (const runHour of AUTOMATIC_RUN_HOURS) {
    const at = runHour * SECONDS_PER_HOUR;
    if (at > elapsed) return { hour: runHour, seconds: at - elapsed };
  }
  const first = AUTOMATIC_RUN_HOURS[0];
  return { hour: first, seconds: SECONDS_PER_DAY - elapsed + first * SECONDS_PER_HOUR };
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

/**
 * Ficha de una corrida automática: «Corrida 07:00 · 305 notas».
 */
export function runLabel(search: Pick<Search, 'scheduled_for' | 'results_count'>): string {
  const hour = search.scheduled_for ? ` ${RUN_CLOCK.format(new Date(search.scheduled_for))}` : '';
  return `Corrida${hour} · ${String(search.results_count)} notas`;
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
  search: Pick<Search, 'concepts' | 'region_name' | 'date_from' | 'date_to'>,
): string {
  const days = spanDays(search.date_from, search.date_to);
  const concepts = search.concepts.map((c) => shortConcept(c.name)).join(' + ');
  return `${concepts} · ${search.region_name} · ${String(days)} ${days === 1 ? 'día' : 'días'}`;
}

// Cuántas misiones recientes caben en la consola sin saturarla.
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
  geocode: 'Mapa',
  filter: 'Región',
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
 * @example missionLog(busqueda) // ['Plan: 4 consultas', 'Fuentes consultadas: 102 notas', …]
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
        ? `Fuentes consultadas: ${String(progress.articles)} notas`
        : 'Consultando fuentes…',
    );
  }
  if (at('extract')) lines.push(STAGE_LABEL.extract ?? 'Leyendo notas');
  if (at('enrich')) {
    const pending = (progress.articles ?? 0) - (progress.reused ?? 0);
    const reused = progress.reused ? ` · ${String(progress.reused)} ya conocidas` : '';
    lines.push(`IA: ${String(progress.enriched ?? 0)} de ${String(Math.max(0, pending))}${reused}`);
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
