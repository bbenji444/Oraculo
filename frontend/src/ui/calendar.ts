/**
 * Cálculos del calendario `HudDatePicker` (28/10/2026): la cuadrícula de un
 * mes, moverse de día en día y escribir las fechas como las lee un analista.
 *
 * Las fechas van como texto `AAAA-MM-DD`, igual que el `<input type="date">`
 * al que reemplaza y que el resto de la búsqueda (store/explorer.ts). Se
 * calcula en UTC para que el cambio de horario no mueva ningún día.
 *
 * Funciones puras (sin DOM), para probarlas sin navegador.
 *
 * No hace: no dibuja ni sabe qué rango eligió la persona.
 */

/** Días que muestra la cuadrícula: 6 semanas, siempre el mismo alto. */
export const GRID_DAYS = 42;
const DAYS_PER_WEEK = 7;
const MS_PER_DAY = 86_400_000;

/** Encabezados de la semana, de lunes a domingo (como en México). */
export const WEEKDAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'] as const;

const MONTHS = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
] as const;

export interface CalendarDay {
  /** `AAAA-MM-DD`. */
  iso: string;
  /** Número del día (1 a 31). */
  day: number;
  /** Si es del mes que se está viendo (los demás van tenues). */
  inMonth: boolean;
}

/** Mes que se ve: año y mes de 0 (enero) a 11. */
export interface MonthView {
  year: number;
  month: number;
}

function toIso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function fromIso(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

/** Si el texto es una fecha `AAAA-MM-DD` que existe. */
export function isIsoDate(text: string | undefined): text is string {
  if (!text || !/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
  return toIso(fromIso(text)) === text;
}

/** El mes en que cae una fecha. */
export function monthOf(iso: string): MonthView {
  const date = fromIso(iso);
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() };
}

/** El mes `delta` meses antes o después. */
export function shiftMonth(view: MonthView, delta: number): MonthView {
  const total = view.year * 12 + view.month + delta;
  return { year: Math.floor(total / 12), month: ((total % 12) + 12) % 12 };
}

/** «octubre de 2026». */
export function monthTitle(view: MonthView): string {
  return `${MONTHS[view.month] ?? ''} de ${String(view.year)}`;
}

/**
 * Los 42 días que se dibujan para un mes, empezando en lunes.
 *
 * @example monthGrid({ year: 2026, month: 9 })[0] // { iso: '2026-09-28', day: 28, inMonth: false }
 */
export function monthGrid(view: MonthView): CalendarDay[] {
  const first = new Date(Date.UTC(view.year, view.month, 1));
  // getUTCDay: 0 es domingo; la semana de México empieza en lunes.
  const offset = (first.getUTCDay() + DAYS_PER_WEEK - 1) % DAYS_PER_WEEK;
  const start = first.getTime() - offset * MS_PER_DAY;
  return Array.from({ length: GRID_DAYS }, (_, index) => {
    const date = new Date(start + index * MS_PER_DAY);
    return {
      iso: toIso(date),
      day: date.getUTCDate(),
      inMonth: date.getUTCMonth() === view.month,
    };
  });
}

/** La fecha `delta` días antes o después. */
export function addDays(iso: string, delta: number): string {
  return toIso(new Date(fromIso(iso).getTime() + delta * MS_PER_DAY));
}

/** «28/10/2026», como lo escriben los analistas. */
export function shortDate(iso: string): string {
  const [year, month, day] = iso.split('-');
  return `${day ?? ''}/${month ?? ''}/${year ?? ''}`;
}

/** «28 de octubre de 2026», para el lector de pantalla. */
export function longDate(iso: string): string {
  const { year, month } = monthOf(iso);
  return `${String(fromIso(iso).getUTCDate())} de ${MONTHS[month] ?? ''} de ${String(year)}`;
}

/** Si `iso` queda fuera de `[min, max]` (los dos son opcionales). */
export function outOfBounds(iso: string, min?: string, max?: string): boolean {
  return (min !== undefined && iso < min) || (max !== undefined && iso > max);
}

/** Hoy en la Ciudad de México, `AAAA-MM-DD` (el monitor trabaja en esa hora). */
export function todayInMexico(now: Date = new Date()): string {
  // en-CA escribe AAAA-MM-DD.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Mexico_City',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}
