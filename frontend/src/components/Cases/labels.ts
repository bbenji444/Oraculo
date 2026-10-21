/**
 * Textos y colores de la sección Casos (Fase 9.3).
 *
 * La API ya trae las etiquetas de estado y sensibilidad en español
 * (`status_label`, `sensitivity_label`); aquí viven las opciones del
 * formulario, el color de cada insignia y el resumen de un renglón.
 *
 * No hace: no pide datos (eso es `hooks/useCases`).
 */
import type { Case, CaseStatus, Sensitivity } from '../../services/cases';
import { formatDay } from '../Explore/format';

/** Opciones del formulario, de menor a mayor reserva. */
export const SENSITIVITY_OPTIONS: { value: Sensitivity; label: string }[] = [
  { value: 'normal', label: 'Normal' },
  { value: 'restricted', label: 'Reservado' },
  { value: 'confidential', label: 'Confidencial' },
];

/** Color de la insignia de sensibilidad: más cálido, más reserva. */
export const SENSITIVITY_TONE: Record<Sensitivity, string> = {
  normal: 'bg-slate-700/70 text-slate-200',
  restricted: 'bg-amber-500/20 text-amber-200',
  confidential: 'bg-rose-500/20 text-rose-200',
};

/** Color de la insignia de estado. */
export const STATUS_TONE: Record<CaseStatus, string> = {
  open: 'bg-emerald-500/20 text-emerald-200',
  closed: 'bg-slate-700/70 text-slate-300',
  archived: 'bg-slate-800 text-slate-400',
};

/**
 * Renglón de resumen de un caso en la lista.
 *
 * @example caseSummary({ article_count: 8, updated_at: '2026-10-21T16:40:42Z' })
 * // '8 notas · actualizado 21 oct'
 */
export function caseSummary(item: Pick<Case, 'article_count' | 'updated_at'>): string {
  const notes =
    item.article_count === 0
      ? 'sin notas todavía'
      : `${String(item.article_count)} ${item.article_count === 1 ? 'nota' : 'notas'}`;
  return `${notes} · actualizado ${formatDay(item.updated_at)}`;
}
