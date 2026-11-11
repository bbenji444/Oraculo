/**
 * Selección para revisar en bloque en un caso (F12, ADR-0107).
 *
 * Benji pidió (11/11/2026) poder «seleccionar todo» en lugar de confirmar una
 * cosa a la vez. Aquí vive la lógica de la selección, sin React, para
 * probarla sola: marcar o desmarcar un grupo completo, saber si un grupo está
 * marcado a medias, qué se manda al confirmar personas en bloque (D1) y cómo
 * se resume lo elegido.
 *
 * No hace: no llama a la API (eso es `hooks/useEntities` y
 * `hooks/useRelationships`).
 */
import type {
  BulkAction,
  BulkReviewResult,
  Entity,
  EntityDecision,
  LegalStatus,
} from '../../services/entities';
import { effectiveLegal, TYPE_GROUP_LABEL } from './grouping';

/** Si un grupo está marcado completo, a medias o nada (para su casilla). */
export type SelectionState = 'none' | 'some' | 'all';

/** Cómo está marcado un grupo de llaves dentro de la selección. */
export function selectionState<K>(selected: ReadonlySet<K>, keys: readonly K[]): SelectionState {
  const marked = keys.filter((key) => selected.has(key)).length;
  if (marked === 0) return 'none';
  return marked === keys.length ? 'all' : 'some';
}

/**
 * La casilla de un grupo: si ya estaba completo lo desmarca; si no, lo
 * completa. Lo demás de la selección no cambia.
 *
 * @example toggleKeys(new Set([1]), [1, 2]) // Set {1, 2}
 */
export function toggleKeys<K>(selected: ReadonlySet<K>, keys: readonly K[]): Set<K> {
  const next = new Set(selected);
  if (selectionState(selected, keys) === 'all') {
    for (const key of keys) next.delete(key);
  } else {
    for (const key of keys) next.add(key);
  }
  return next;
}

/** Marca o desmarca una sola llave. */
export function toggleKey<K>(selected: ReadonlySet<K>, key: K, checked: boolean): Set<K> {
  const next = new Set(selected);
  if (checked) next.add(key);
  else next.delete(key);
  return next;
}

/**
 * Qué se manda al confirmar o descartar en bloque.
 *
 * Al confirmar, cada persona queda con el estatus legal que se ve en su
 * renglón: el que eligió el analista en el menú o, si no lo tocó, el
 * confirmado o el que sugirió la IA; si la nota no dice nada, «mencionado»
 * (D1 del plan). Lo que no es persona y lo que se descarta no lleva estatus.
 *
 * @param entities Las entidades elegidas.
 * @param action Confirmar o descartar.
 * @param chosen El estatus que el analista eligió a mano, por entidad.
 * @returns Una decisión por entidad, en el mismo orden.
 */
export function bulkDecisions(
  entities: readonly Entity[],
  action: 'confirm' | 'discard',
  chosen: ReadonlyMap<number, LegalStatus>,
): EntityDecision[] {
  return entities.map((entity) => ({
    entity_id: entity.id,
    legal_status:
      action === 'confirm' && entity.type === 'person'
        ? (chosen.get(entity.id) ?? effectiveLegal(entity) ?? 'mentioned')
        : null,
  }));
}

/**
 * Lo elegido en palabras, por tipo, en el orden en que llega (el de la
 * pantalla).
 *
 * @example selectionSummary([juan, ana, fgr]) // '2 personas y 1 organización'
 */
export function selectionSummary(entities: readonly Pick<Entity, 'type' | 'type_label'>[]): string {
  const counts = new Map<string, { count: number; singular: string }>();
  for (const entity of entities) {
    const current = counts.get(entity.type);
    if (current) current.count += 1;
    else counts.set(entity.type, { count: 1, singular: entity.type_label });
  }
  const parts = [...counts.entries()].map(([type, { count, singular }]) => {
    const plural = (TYPE_GROUP_LABEL[type] ?? `${singular}s`).toLowerCase();
    return `${String(count)} ${count === 1 ? singular : plural}`;
  });
  const last = parts.pop();
  if (last === undefined) return '';
  return parts.length === 0 ? last : `${parts.join(', ')} y ${last}`;
}

/**
 * El aviso después de revisar en bloque.
 *
 * @example bulkNotice('confirm', { changed: 5, unchanged: 2 })
 * // 'Listo: se confirmaron 5. 2 ya estaban así.'
 */
export function bulkNotice(action: BulkAction, result: BulkReviewResult): string {
  const one = result.changed === 1;
  const verb =
    action === 'confirm'
      ? one
        ? 'se confirmó'
        : 'se confirmaron'
      : one
        ? 'se descartó'
        : 'se descartaron';
  const done = `Listo: ${verb} ${String(result.changed)}.`;
  if (result.unchanged === 0) return done;
  const already = result.unchanged === 1 ? 'ya estaba así' : 'ya estaban así';
  return `${done} ${String(result.unchanged)} ${already}.`;
}

/** «1 vínculo», «3 vínculos». */
export function countLabel(count: number, singular: string, plural: string): string {
  return `${String(count)} ${count === 1 ? singular : plural}`;
}
