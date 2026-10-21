/**
 * Textos y colores de la sección Casos (Fases 9.3 a 9.5).
 *
 * La API ya trae las etiquetas de estado y sensibilidad en español
 * (`status_label`, `sensitivity_label`); aquí viven las opciones del
 * formulario, el color de cada insignia y el resumen de un renglón.
 *
 * No hace: no pide datos (eso es `hooks/useCases`).
 */
import type { Case, CaseStatus, Sensitivity } from '../../services/cases';
import type { ResolutionAction } from '../../hooks/useResolution';
import type { Entity, LegalStatus } from '../../services/entities';
import type {
  Relationship,
  RelationshipDraft,
  RelationshipType,
} from '../../services/relationships';
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

/** Estatus legales que puede elegir quien confirma (los de la API, ADR-0105). */
export const LEGAL_STATUS_OPTIONS: { value: LegalStatus; label: string }[] = [
  { value: 'mentioned', label: 'mencionado' },
  { value: 'alleged', label: 'señalado' },
  { value: 'detained', label: 'detenido' },
  { value: 'charged', label: 'vinculado a proceso' },
  { value: 'victim', label: 'víctima' },
  { value: 'witness', label: 'testigo' },
  { value: 'official', label: 'funcionario' },
];

/** Un tipo de vínculo en el formulario «Nuevo vínculo» (Fase 9.5). */
export interface RelationshipTypeOption {
  value: RelationshipType;
  label: string;
  /** Si importa el sentido: «A es dueño de B» no es «B es dueño de A». */
  directed: boolean;
}

/** Los tipos de la API (`RELATIONSHIP_LABEL`), los más usados primero. */
export const RELATIONSHIP_TYPE_OPTIONS: RelationshipTypeOption[] = [
  { value: 'associate', label: 'asociado', directed: false },
  { value: 'family', label: 'familiar', directed: false },
  { value: 'same_event', label: 'mismo hecho', directed: false },
  { value: 'appears_with', label: 'aparecen juntas', directed: false },
  { value: 'owns', label: 'es dueño de', directed: true },
  { value: 'employer', label: 'es empleador de', directed: true },
  { value: 'located_in', label: 'está ubicado en', directed: true },
  // En la base «otro» no es simétrico: se guarda en el sentido en que se escribió.
  { value: 'custom', label: 'otro (etiqueta propia)', directed: true },
];

// Los mismos límites que valida el backend (domain/relationships.py).
export const CUSTOM_LABEL_MAX_CHARS = 80;
export const RELATIONSHIP_NOTES_MAX_CHARS = 1000;

/**
 * Qué le falta a un «Nuevo vínculo» antes de mandarlo, o `null` si está listo.
 *
 * @example draftProblem({ entityA: 1, entityB: 1, type: 'family', customLabel: '', notes: '' })
 * // 'Elige dos entidades distintas.'
 */
export function draftProblem(draft: RelationshipDraft): string | null {
  if (!draft.entityA || !draft.entityB) return 'Elige las dos entidades.';
  if (draft.entityA === draft.entityB) return 'Elige dos entidades distintas.';
  const label = draft.customLabel.trim();
  if (draft.type === 'custom' && !label) return 'Escribe la etiqueta del vínculo.';
  if (label.length > CUSTOM_LABEL_MAX_CHARS) {
    return `La etiqueta admite hasta ${String(CUSTOM_LABEL_MAX_CHARS)} caracteres.`;
  }
  if (draft.notes.trim().length > RELATIONSHIP_NOTES_MAX_CHARS) {
    return `La nota admite hasta ${String(RELATIONSHIP_NOTES_MAX_CHARS)} caracteres.`;
  }
  return null;
}

/** "70 %": la confianza de un vínculo para leerla de un vistazo. */
export function confidencePercent(confidence: number): string {
  return `${String(Math.round(confidence * 100))} %`;
}

/**
 * Cómo se lee un vínculo en una línea: con flecha si importa el sentido.
 *
 * @example relationshipPhrase({ type: 'owns', type_label: 'es dueño de', custom_label: null, symmetric: false })
 * // '→ es dueño de →'
 */
export function relationshipPhrase(
  r: Pick<Relationship, 'type' | 'type_label' | 'custom_label' | 'symmetric'>,
): string {
  const text = r.type === 'custom' && r.custom_label ? r.custom_label : r.type_label;
  return r.symmetric ? `— ${text} —` : `→ ${text} →`;
}

/**
 * Qué se manda al elegir «Es la misma que…» en una tarjeta (Fase 9.5).
 *
 * Queda la confirmada, si una lo está (el backend no deja que una sugerida
 * absorba a una confirmada); si están igual, queda la elegida en la lista.
 *
 * @example mergeAction({ id: 4, review_status: 'suggested' }, { id: 9, review_status: 'confirmed' })
 * // { kind: 'merge', keepId: 9, mergeId: 4 }
 */
export function mergeAction(
  entity: Pick<Entity, 'id' | 'review_status'>,
  target: Pick<Entity, 'id' | 'review_status'>,
): ResolutionAction {
  const keepThis = entity.review_status === 'confirmed' && target.review_status !== 'confirmed';
  return keepThis
    ? { kind: 'merge', keepId: entity.id, mergeId: target.id }
    : { kind: 'merge', keepId: target.id, mergeId: entity.id };
}
