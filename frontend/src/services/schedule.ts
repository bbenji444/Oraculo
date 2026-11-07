/**
 * Servicio del horario único de las corridas (`/api/v1/schedule`; docs/api.md, ADR-0040).
 *
 * Un solo horario para todos, que maneja el administrador. A cada hora se hace
 * una corrida nueva (búsqueda + IA + PDF) con lo publicado desde la hora
 * anterior, y su reporte se manda a todos los destinatarios activos.
 *
 * Los componentes nunca llaman a fetch directamente (CLAUDE.md §6.2).
 */
import { apiUrl } from '../config/api';
import { badFormat, requestJson } from './http';

export interface ScheduleInput {
  /** Horas «HH:MM» de la Ciudad de México. */
  times: string[];
  /** 1 = lunes … 7 = domingo; vacío = todos los días. */
  days: number[];
}

export interface Schedule extends ScheduleInput {
  /** Nadie lo ha editado: vale `AUTOMATIC_RUN_HOURS` del servidor. */
  is_default: boolean;
  /** Si el reloj lanza las corridas (`AUTOMATIC_RUNS_ENABLED`). */
  enabled: boolean;
  updated_at: string | null;
  updated_by: string | null;
  /** Próximas corridas (ISO). */
  upcoming: string[];
  /** Costo promedio de una corrida en las últimas dos semanas (USD). */
  average_run_cost_usd: number | null;
  limits: { max_runs_per_day: number; min_gap_minutes: number };
}

function isSchedule(value: unknown): value is Schedule {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return Array.isArray(v.times) && Array.isArray(v.upcoming) && typeof v.limits === 'object';
}

const url = apiUrl('schedule');

/** El horario vigente. */
export async function getSchedule(signal?: AbortSignal): Promise<Schedule> {
  const body = await requestJson(url, { signal });
  if (!isSchedule(body)) throw badFormat();
  return body;
}

/**
 * Reemplaza el horario de todos; aplica en el siguiente minuto.
 *
 * @throws ApiError `invalid_schedule` con `details.problemas` si rompe los topes.
 */
export async function saveSchedule(input: ScheduleInput): Promise<Schedule> {
  const body = await requestJson(url, { method: 'PUT', body: input });
  if (!isSchedule(body)) throw badFormat();
  return body;
}
