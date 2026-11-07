/**
 * Lógica pura de la programación de envíos (ADR-0039): días, horas, a quién
 * manda cada regla y cuáles son los próximos envíos.
 *
 * No hace: no llama a la API.
 */
import type { Recipient, Rule } from '../../services/deliveries';

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
const WORKDAYS = [1, 2, 3, 4, 5];
const DAYS_PER_WEEK = 7;
const MINUTES_PER_HOUR = 60;
const MS_PER_MINUTE = 60_000;
const MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR;

/** Ordena y quita repetidas: «15:00, 07:00, 15:00» → «07:00, 15:00». */
export function sortTimes(times: readonly string[]): string[] {
  return [...new Set(times)].sort();
}

/**
 * Los días de una regla, como se leen.
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

/** Destinatarios activos que reciben una regla. */
export function ruleTargets(rule: Rule, recipients: readonly Recipient[]): Recipient[] {
  const active = recipients.filter((r) => r.is_active && r.email);
  if (rule.audience === 'all') return active.filter((r) => !rule.exclude_ids.includes(r.id));
  return active.filter((r) => rule.recipient_ids.includes(r.id));
}

/** Un envío que va a ocurrir. */
export interface UpcomingSend {
  at: Date;
  rule: Rule;
  recipients: number;
}

// Hora local de la Ciudad de México (UTC−6 todo el año desde octubre de 2022).
const MEXICO_CITY_OFFSET_MINUTES = -6 * MINUTES_PER_HOUR;

function toMinutes(time: string): number {
  const [h = '0', m = '0'] = time.split(':');
  return Number(h) * MINUTES_PER_HOUR + Number(m);
}

/**
 * Los próximos envíos de las reglas prendidas, en orden.
 *
 * @param rules Reglas.
 * @param recipients Destinatarios.
 * @param now Momento actual.
 * @param count Cuántos devolver.
 */
export function upcomingSends(
  rules: readonly Rule[],
  recipients: readonly Recipient[],
  now: Date,
  count: number,
): UpcomingSend[] {
  const result: UpcomingSend[] = [];
  // Minuto actual en la hora de la Ciudad de México.
  const localNow = new Date(now.getTime() + MEXICO_CITY_OFFSET_MINUTES * MS_PER_MINUTE);
  const startOfDay = Date.UTC(
    localNow.getUTCFullYear(),
    localNow.getUTCMonth(),
    localNow.getUTCDate(),
  );
  for (let day = 0; day <= DAYS_PER_WEEK; day += 1) {
    const dayStart = startOfDay + day * MINUTES_PER_DAY * MS_PER_MINUTE;
    const isoDay = ((new Date(dayStart).getUTCDay() + 6) % DAYS_PER_WEEK) + 1;
    for (const rule of rules) {
      if (!rule.is_active || (rule.days.length > 0 && !rule.days.includes(isoDay))) continue;
      const people = ruleTargets(rule, recipients).length;
      if (people === 0) continue;
      for (const time of rule.times) {
        const localMs = dayStart + toMinutes(time) * MS_PER_MINUTE;
        const at = new Date(localMs - MEXICO_CITY_OFFSET_MINUTES * MS_PER_MINUTE);
        if (at > now) result.push({ at, rule, recipients: people });
      }
    }
  }
  return result.sort((a, b) => a.at.getTime() - b.at.getTime()).slice(0, count);
}
