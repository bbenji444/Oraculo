/**
 * Lógica pura del horario único de las corridas (ADR-0040): días, horas, los
 * topes que también revisa el servidor y lo que cuesta al día.
 *
 * Revisar los topes aquí solo sirve para avisar antes de guardar; quien decide
 * es el servidor.
 *
 * No hace: no llama a la API.
 */

/** Días ISO en orden de lunes a domingo, como se leen. */
export const DAYS: readonly { value: number; short: string; long: string }[] = [
  { value: 1, short: 'L', long: 'lunes' },
  { value: 2, short: 'M', long: 'martes' },
  { value: 3, short: 'X', long: 'miércoles' },
  { value: 4, short: 'J', long: 'jueves' },
  { value: 5, short: 'V', long: 'viernes' },
  { value: 6, short: 'S', long: 'sábado' },
  { value: 7, short: 'D', long: 'domingo' },
];
export const WORKDAYS = [1, 2, 3, 4, 5];
const DAYS_PER_WEEK = 7;
const MINUTES_PER_HOUR = 60;
const MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR;

/** Ordena y quita repetidas: «15:00, 07:00, 15:00» → «07:00, 15:00». */
export function sortTimes(times: readonly string[]): string[] {
  return [...new Set(times)].sort();
}

/** «09:30» → 570. */
export function toMinutes(time: string): number {
  const [h = '0', m = '0'] = time.split(':');
  return Number(h) * MINUTES_PER_HOUR + Number(m);
}

/**
 * Los días del horario, como se leen.
 *
 * @example daysLabel([]) // 'todos los días'
 * @example daysLabel([1, 2, 3, 4, 5]) // 'de lunes a viernes'
 */
export function daysLabel(days: readonly number[]): string {
  if (days.length === 0 || days.length === DAYS_PER_WEEK) return 'todos los días';
  if (days.length === WORKDAYS.length && WORKDAYS.every((d) => days.includes(d))) {
    return 'de lunes a viernes';
  }
  const names = DAYS.filter((d) => days.includes(d.value)).map((d) => d.long);
  const plural = (name: string) => (name.endsWith('s') ? name : `${name}s`);
  return names.length === 1
    ? `los ${plural(names[0] ?? '')}`
    : `${names.slice(0, -1).join(', ')} y ${names.at(-1) ?? ''}`;
}

/** Topes del horario (los manda el servidor). */
export interface ScheduleLimits {
  max_runs_per_day: number;
  min_gap_minutes: number;
}

/**
 * Qué tope rompe un horario, en palabras, o `null` si cumple.
 *
 * @example scheduleProblem(['07:00', '07:30'], { max_runs_per_day: 8, min_gap_minutes: 60 })
 * // 'Entre 07:00 y 07:30 debe haber al menos 60 minutos.'
 */
export function scheduleProblem(times: readonly string[], limits: ScheduleLimits): string | null {
  const sorted = sortTimes(times);
  if (sorted.length === 0) return 'Agrega al menos una hora.';
  if (sorted.length > limits.max_runs_per_day) {
    return `Máximo ${String(limits.max_runs_per_day)} horas al día: cada hora es una corrida con IA.`;
  }
  if (sorted.length === 1) return null;
  for (const [index, time] of sorted.entries()) {
    const next = sorted[(index + 1) % sorted.length] ?? time;
    // La última y la primera del día siguiente también deben separarse.
    const gap = (toMinutes(next) - toMinutes(time) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
    if (gap < limits.min_gap_minutes) {
      return `Entre ${time} y ${next} debe haber al menos ${String(limits.min_gap_minutes)} minutos.`;
    }
  }
  return null;
}

/**
 * Lo que cuesta el horario en una semana, con el costo promedio de una corrida.
 *
 * @returns Dólares por semana, o `null` sin costo de referencia.
 */
export function weeklyCost(
  times: readonly string[],
  days: readonly number[],
  costPerRun: number | null,
): number | null {
  if (costPerRun === null) return null;
  const activeDays = days.length === 0 ? DAYS_PER_WEEK : days.length;
  return sortTimes(times).length * activeDays * costPerRun;
}
