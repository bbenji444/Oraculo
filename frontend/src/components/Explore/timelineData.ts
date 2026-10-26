/**
 * Línea del tiempo de Explorar (F12.7, plan F12 §4.6): ordena las notas de la
 * búsqueda por fecha y hora, las junta en tramos (por hora o por día) para
 * ver los picos, y filtra por tramo, estado y categoría.
 *
 * Dos fechas, con dos usos:
 * - **Las barras y el tramo** usan cuándo se **publicó** cada nota: muestran
 *   los picos de cobertura dentro del periodo buscado. (Con la fecha del hecho
 *   el eje se estiraba a meses: un avance de hoy de un caso de 2025.)
 * - **El orden de la tira** usa, por defecto, cuándo **ocurrió** el hecho: si
 *   la IA dedujo la fecha del hecho (`event_date`), esa; si no, la de
 *   publicación. Cada nota dice cuál se usó. El analista puede cambiarlo.
 *
 * Los tramos se cortan en hora de la Ciudad de México (UTC-6 todo el año desde
 * 2022): un pico «de las 15:00» es de las 15:00 en la CDMX.
 *
 * No hace: no dibuja ni pide datos; solo calcula (lo usa `Timeline.tsx`).
 */
import type { Article } from '../../services/searches';

/** Diferencia de la CDMX con UTC, en milisegundos (sin horario de verano). */
const MEXICO_CITY_OFFSET_MS = -6 * 60 * 60 * 1000;
const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
/** Hasta este lapso los tramos son por hora; con más, por día (si no, son demasiados). */
const HOURLY_UP_TO_MS = 3 * DAY_MS;
/** La fecha del hecho trae solo el día: se ubica a mediodía para no caer en el día de al lado. */
const EVENT_DATE_HOUR = 12;
/** Cuántos picos se resaltan. */
const PEAKS = 3;

/** Claves INEGI de los 32 estados, para el filtro y los rótulos. */
export const STATE_NAMES: Readonly<Record<string, string>> = {
  '01': 'Aguascalientes',
  '02': 'Baja California',
  '03': 'Baja California Sur',
  '04': 'Campeche',
  '05': 'Coahuila',
  '06': 'Colima',
  '07': 'Chiapas',
  '08': 'Chihuahua',
  '09': 'Ciudad de México',
  '10': 'Durango',
  '11': 'Guanajuato',
  '12': 'Guerrero',
  '13': 'Hidalgo',
  '14': 'Jalisco',
  '15': 'Estado de México',
  '16': 'Michoacán',
  '17': 'Morelos',
  '18': 'Nayarit',
  '19': 'Nuevo León',
  '20': 'Oaxaca',
  '21': 'Puebla',
  '22': 'Querétaro',
  '23': 'Quintana Roo',
  '24': 'San Luis Potosí',
  '25': 'Sinaloa',
  '26': 'Sonora',
  '27': 'Tabasco',
  '28': 'Tamaulipas',
  '29': 'Tlaxcala',
  '30': 'Veracruz',
  '31': 'Yucatán',
  '32': 'Zacatecas',
};

export type MomentKind = 'event' | 'published';

/** Con qué fecha se ordena la tira: la del hecho (si la hay) o la de publicación. */
export type OrderBasis = 'event' | 'published';

export interface NoteMoment {
  /** Milisegundos UTC. */
  at: number;
  /** Si es la fecha del hecho (deducida por la IA) o la de publicación. */
  kind: MomentKind;
}

export type TimelineUnit = 'hour' | 'day';

export interface TimelineBucket {
  /** Inicio del tramo (milisegundos UTC). */
  start: number;
  end: number;
  /** Notas del tramo, de la más vieja a la más nueva. */
  articleIds: number[];
  /** Si es uno de los picos. */
  peak: boolean;
}

export interface Timeline {
  unit: TimelineUnit;
  buckets: TimelineBucket[];
  /** La más alta, para escalar las barras. */
  max: number;
  /** Notas que no tienen ninguna fecha (no entran en la línea). */
  undated: number;
}

export interface TimelineFilters {
  /** Tramo elegido: `[inicio, fin)` en milisegundos UTC. */
  range: readonly [number, number] | null;
  categoryId: number | null;
  /** Clave INEGI del estado (`08`). */
  stateCode: string | null;
}

export const NO_FILTERS: TimelineFilters = { range: null, categoryId: null, stateCode: null };

/**
 * Cuándo ocurrió una nota: la fecha del hecho si la hay, si no la de publicación.
 *
 * @returns El momento, o `null` si la nota no trae ninguna fecha.
 */
export function noteMoment(
  article: Pick<Article, 'event_date' | 'published_at'>,
): NoteMoment | null {
  if (article.event_date) {
    const [year, month, day] = article.event_date.split('-').map(Number);
    if (year && month && day) {
      const localNoon = Date.UTC(year, month - 1, day, EVENT_DATE_HOUR);
      return { at: localNoon - MEXICO_CITY_OFFSET_MS, kind: 'event' };
    }
  }
  if (article.published_at) {
    return { at: new Date(article.published_at).getTime(), kind: 'published' };
  }
  return null;
}

/** Cuándo se publicó una nota (milisegundos UTC), o `null` si no se sabe. */
export function publishedAt(article: Pick<Article, 'published_at'>): number | null {
  return article.published_at ? new Date(article.published_at).getTime() : null;
}

/** El momento con que se ordena una nota según la base elegida. */
export function momentFor(
  article: Pick<Article, 'event_date' | 'published_at'>,
  basis: OrderBasis,
): NoteMoment | null {
  if (basis === 'event') return noteMoment(article);
  const at = publishedAt(article);
  return at === null ? null : { at, kind: 'published' };
}

/** Inicio del tramo que contiene `at`, en hora de la CDMX. */
function floorTo(at: number, unit: TimelineUnit): number {
  const size = unit === 'hour' ? HOUR_MS : DAY_MS;
  const local = at + MEXICO_CITY_OFFSET_MS;
  return Math.floor(local / size) * size - MEXICO_CITY_OFFSET_MS;
}

/**
 * Arma la línea del tiempo por fecha de publicación: un tramo por hora (si todo
 * cabe en 3 días) o por día.
 *
 * Incluye los tramos vacíos entre la primera y la última nota, para que los
 * huecos se vean como huecos.
 */
export function buildTimeline(articles: readonly Article[]): Timeline {
  const dated = articles
    .map((a) => ({ id: a.article_id, at: publishedAt(a) }))
    .filter((x): x is { id: number; at: number } => x.at !== null)
    .map((x) => ({ id: x.id, moment: { at: x.at, kind: 'published' as const } }))
    .sort((a, b) => a.moment.at - b.moment.at || a.id - b.id);
  const undated = articles.length - dated.length;
  const first = dated[0];
  const last = dated[dated.length - 1];
  if (!first || !last) {
    return { unit: 'hour', buckets: [], max: 0, undated };
  }
  const unit: TimelineUnit = last.moment.at - first.moment.at <= HOURLY_UP_TO_MS ? 'hour' : 'day';
  const size = unit === 'hour' ? HOUR_MS : DAY_MS;
  const buckets: TimelineBucket[] = [];
  for (let start = floorTo(first.moment.at, unit); start <= last.moment.at; start += size) {
    buckets.push({ start, end: start + size, articleIds: [], peak: false });
  }
  for (const note of dated) {
    const index = Math.floor((note.moment.at - (buckets[0]?.start ?? 0)) / size);
    buckets[index]?.articleIds.push(note.id);
  }
  const max = Math.max(...buckets.map((b) => b.articleIds.length));
  [...buckets]
    .filter((b) => b.articleIds.length > 0)
    .sort((a, b) => b.articleIds.length - a.articleIds.length || a.start - b.start)
    .slice(0, PEAKS)
    .forEach((b) => {
      b.peak = true;
    });
  return { unit, buckets, max, undated };
}

/** Clave INEGI del estado de la ubicación principal (`08` de `08019`), o `null`. */
export function stateCodeOf(article: Pick<Article, 'primary_location'>): string | null {
  const code = article.primary_location?.region_code ?? null;
  if (!code || !/^\d{2}/.test(code)) {
    return null;
  }
  const state = code.slice(0, 2);
  return state in STATE_NAMES ? state : null;
}

/** Aplica los filtros de la línea del tiempo (los mismos para el globo y la lista). */
export function applyTimeline(articles: readonly Article[], filters: TimelineFilters): Article[] {
  const { range, categoryId, stateCode } = filters;
  if (!range && categoryId === null && stateCode === null) {
    return [...articles];
  }
  return articles.filter((article) => {
    if (categoryId !== null && article.category?.id !== categoryId) return false;
    if (stateCode !== null && stateCodeOf(article) !== stateCode) return false;
    if (range) {
      // El tramo es de publicación, igual que las barras.
      const at = publishedAt(article);
      if (at === null || at < range[0] || at >= range[1]) return false;
    }
    return true;
  });
}

/** Las notas en orden cronológico según la base elegida (las sin fecha al final). */
export function chronological(
  articles: readonly Article[],
  basis: OrderBasis = 'event',
): Article[] {
  return [...articles].sort((a, b) => {
    const ma = momentFor(a, basis)?.at ?? Number.POSITIVE_INFINITY;
    const mb = momentFor(b, basis)?.at ?? Number.POSITIVE_INFINITY;
    return ma - mb || a.article_id - b.article_id;
  });
}

/** Estados presentes en las notas, con cuántas tiene cada uno (de más a menos). */
export function statesIn(
  articles: readonly Article[],
): { code: string; name: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const article of articles) {
    const code = stateCodeOf(article);
    if (code) counts.set(code, (counts.get(code) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([code, count]) => ({ code, name: STATE_NAMES[code] ?? code, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'es'));
}

/** Categorías presentes en las notas, con cuántas tiene cada una (de más a menos). */
export function categoriesIn(
  articles: readonly Article[],
): { id: number; name: string; count: number }[] {
  const counts = new Map<number, { name: string; count: number }>();
  for (const article of articles) {
    const category = article.category;
    if (!category) continue;
    const current = counts.get(category.id);
    counts.set(category.id, { name: category.name, count: (current?.count ?? 0) + 1 });
  }
  return [...counts.entries()]
    .map(([id, value]) => ({ id, ...value }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'es'));
}

/** Hasta cuántas historias se apilan en un tramo; las demás se cuentan en «+N». */
export const MAX_BEADS_PER_BUCKET = 4;

/** Una historia como punto de la línea del tiempo (el mismo hecho en varios medios = un punto). */
export interface Bead {
  /** La nota que representa a la historia: la primera que se publicó. */
  lead: Article;
  /** Todas sus notas (medios), incluida la principal. */
  articleIds: number[];
  /** Cuándo se publicó la principal (milisegundos UTC). */
  at: number;
  /** Tramo de la línea del tiempo en el que cae. */
  bucket: number;
  /** Lugar en la pila del tramo (0 = abajo). */
  row: number;
}

export interface BeadLayout {
  beads: Bead[];
  /** Historias que no caben en la pila, por tramo. */
  overflow: Map<number, number>;
}

/**
 * Acomoda las historias en la línea del tiempo, sin repetir el mismo hecho.
 *
 * Las notas de una misma historia (`story_id`, ADR-0026) se juntan en un solo
 * punto; en cada tramo se apilan de la que tiene más medios a la que menos.
 *
 * @param articles Notas visibles (ya filtradas).
 * @param timeline La línea del tiempo de esas notas (`buildTimeline`).
 * @returns Los puntos y cuántas historias quedaron fuera de cada pila.
 */
export function layoutBeads(articles: readonly Article[], timeline: Timeline): BeadLayout {
  const first = timeline.buckets[0];
  const overflow = new Map<number, number>();
  if (!first) return { beads: [], overflow };
  const size = timeline.unit === 'hour' ? HOUR_MS : DAY_MS;
  const byStory = new Map<number, Article[]>();
  for (const article of chronological(articles, 'published')) {
    if (publishedAt(article) === null) continue;
    const key = article.story_id ?? -article.article_id;
    byStory.set(key, [...(byStory.get(key) ?? []), article]);
  }
  const byBucket = new Map<number, Omit<Bead, 'row'>[]>();
  for (const notes of byStory.values()) {
    const lead = notes[0];
    if (!lead) continue;
    const at = publishedAt(lead) ?? 0;
    const bucket = Math.min(
      Math.max(0, Math.floor((at - first.start) / size)),
      timeline.buckets.length - 1,
    );
    const item = { lead, articleIds: notes.map((n) => n.article_id), at, bucket };
    byBucket.set(bucket, [...(byBucket.get(bucket) ?? []), item]);
  }
  const beads: Bead[] = [];
  for (const [bucket, items] of byBucket) {
    items.sort((a, b) => b.articleIds.length - a.articleIds.length || a.at - b.at);
    items.slice(0, MAX_BEADS_PER_BUCKET).forEach((item, row) => beads.push({ ...item, row }));
    if (items.length > MAX_BEADS_PER_BUCKET) {
      overflow.set(bucket, items.length - MAX_BEADS_PER_BUCKET);
    }
  }
  return { beads: beads.sort((a, b) => a.at - b.at), overflow };
}
