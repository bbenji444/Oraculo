/**
 * Cómo se ordena y se agrupa lo que la IA encontró en un caso (F12, ADR-0107).
 *
 * Benji pidió (11/11/2026) que la información del caso se divida de forma
 * clara y útil. Aquí vive esa lógica, sin React, para probarla sola:
 *
 * - Las entidades se agrupan por tipo (Personas, Organizaciones, Vehículos…)
 *   en el orden en que más sirven a una investigación.
 * - Dentro de cada grupo van primero las que **participan en el hecho** de
 *   alguna nota (la IA lo marca en cada mención con `role = event`) y después
 *   las que solo se nombran. En personas, además, por estatus legal: un
 *   detenido importa antes que alguien solo mencionado.
 * - Los vínculos se parten en fuertes y débiles según `strength`, que calcula
 *   el backend.
 *
 * No hace: no pide datos ni decide nada (solo ordena lo que recibe).
 */
import type { Entity, LegalStatus } from '../../services/entities';
import type { Relationship } from '../../services/relationships';

/** Orden de los grupos: quién y con qué, antes que dónde. */
export const TYPE_ORDER: readonly string[] = [
  'person',
  'org',
  'vehicle',
  'account',
  'phone',
  'place',
  'other',
];

/** Nombre de cada grupo (los tipos de `ENTITY_TYPE_LABEL` del backend, en plural). */
export const TYPE_GROUP_LABEL: Readonly<Record<string, string>> = {
  person: 'Personas',
  org: 'Organizaciones',
  vehicle: 'Vehículos',
  account: 'Cuentas',
  phone: 'Teléfonos',
  place: 'Lugares',
  other: 'Otros',
};

/**
 * Orden de los estatus legales al investigar (ADR-0105): primero quien ya
 * está en un proceso, al final quien solo se menciona.
 */
export const LEGAL_PRIORITY: readonly LegalStatus[] = [
  'charged',
  'detained',
  'alleged',
  'victim',
  'witness',
  'official',
  'mentioned',
];

/** Un grupo de entidades del mismo tipo, ya ordenado. */
export interface EntityGroup {
  type: string;
  label: string;
  items: Entity[];
  /** Cuántas participan en el hecho de alguna nota. */
  inEvent: number;
}

/**
 * El estatus legal con el que se muestra una persona: el confirmado o, si
 * nadie lo ha confirmado, el que sugirió la IA. Nulo si la nota no lo dice.
 */
export function effectiveLegal(
  entity: Pick<Entity, 'legal_status' | 'suggested_legal_status'>,
): LegalStatus | null {
  return entity.legal_status ?? entity.suggested_legal_status;
}

/** Si la entidad participa en el hecho de al menos una nota (no solo se nombra). */
export function participatesInEvent(entity: Pick<Entity, 'mentions'>): boolean {
  return entity.mentions.some((m) => m.role === 'event');
}

function legalRank(entity: Entity): number {
  if (entity.type !== 'person') return LEGAL_PRIORITY.length;
  // «La nota no lo dice» cuenta como «mencionado» (D1 del plan).
  return LEGAL_PRIORITY.indexOf(effectiveLegal(entity) ?? 'mentioned');
}

function typeRank(type: string): number {
  const index = TYPE_ORDER.indexOf(type);
  return index === -1 ? TYPE_ORDER.length : index;
}

function compareEntities(a: Entity, b: Entity): number {
  return (
    Number(participatesInEvent(b)) - Number(participatesInEvent(a)) ||
    legalRank(a) - legalRank(b) ||
    b.article_count - a.article_count ||
    b.mention_count - a.mention_count ||
    a.label.localeCompare(b.label, 'es')
  );
}

/**
 * Agrupa las entidades por tipo, en el orden de `TYPE_ORDER`.
 *
 * @param entities Las entidades de un estado (sugeridas, confirmadas…).
 * @returns Un grupo por tipo presente, cada uno ordenado: primero las que
 *   participan en el hecho, luego por estatus legal (personas), notas y
 *   menciones. Un tipo que el frontend no conoce va al final con su
 *   `type_label`.
 *
 * @example groupByType([camioneta, juan, fgr]).map((g) => g.label)
 * // ['Personas', 'Organizaciones', 'Vehículos']
 */
export function groupByType(entities: readonly Entity[]): EntityGroup[] {
  const byType = new Map<string, Entity[]>();
  for (const entity of entities) {
    const items = byType.get(entity.type);
    if (items) items.push(entity);
    else byType.set(entity.type, [entity]);
  }
  return [...byType.entries()]
    .sort(([a], [b]) => typeRank(a) - typeRank(b) || a.localeCompare(b))
    .map(([type, items]) => {
      const sorted = [...items].sort(compareEntities);
      return {
        type,
        label: TYPE_GROUP_LABEL[type] ?? sorted[0]?.type_label ?? type,
        items: sorted,
        inEvent: sorted.filter(participatesInEvent).length,
      };
    });
}

/**
 * Parte los vínculos en fuertes (participan en el mismo hecho o los dibujó
 * una persona) y débiles (solo se mencionan juntas). Conserva el orden que
 * trae la API.
 */
export function splitByStrength(relationships: readonly Relationship[]): {
  strong: Relationship[];
  weak: Relationship[];
} {
  return {
    strong: relationships.filter((r) => r.strength === 'strong'),
    weak: relationships.filter((r) => r.strength !== 'strong'),
  };
}

/** Llave única de un vínculo en pantalla (un sugerido todavía no tiene id). */
export function relationshipKey(r: Pick<Relationship, 'entity_a' | 'entity_b' | 'type'>): string {
  return `${String(r.entity_a.id)}-${String(r.entity_b.id)}-${r.type}`;
}
