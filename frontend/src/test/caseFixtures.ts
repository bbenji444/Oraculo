/**
 * Entidades y vínculos de mentira para las pruebas de Casos (F12).
 *
 * Arman objetos con la forma exacta de la API (`services/entities` y
 * `services/relationships`) pidiendo solo lo que cada prueba necesita. No se
 * incluye en el build.
 */
import type { Entity, LegalStatus, Mention } from '../services/entities';
import type { LinkStrength, Relationship } from '../services/relationships';

let nextMention = 1;

/** Una cita de una nota con el papel que le dio la IA. */
export function mention(role: Mention['role']): Mention {
  const id = nextMention++;
  return {
    id,
    entity_id: 0,
    article_id: 1,
    article_title: 'Nota',
    article_url: 'https://x.mx/1',
    source_name: null,
    published_at: null,
    mention_text: 'x',
    role,
    legal_status_hint: null,
    legal_status_hint_label: null,
    confidence: 0.9,
    evidence_span: 'x',
  };
}

export interface EntityOptions {
  /** Papel de cada mención; una mención «solo se nombra» si no se dice. */
  roles?: Mention['role'][];
  legal?: LegalStatus | null;
  suggested?: LegalStatus | null;
  articles?: number;
  typeLabel?: string;
}

/** Una entidad sugerida del caso. */
export function entity(
  id: number,
  type: string,
  label: string,
  options: EntityOptions = {},
): Entity {
  const roles = options.roles ?? ['mentioned'];
  return {
    id,
    type,
    type_label: options.typeLabel ?? type,
    label,
    aliases: [],
    review_status: 'suggested',
    review_status_label: 'sugerida',
    legal_status: options.legal ?? null,
    legal_status_label: null,
    suggested_legal_status: options.suggested ?? null,
    suggested_legal_status_label: null,
    reviewed_by: null,
    reviewed_at: null,
    region_id: null,
    region_name: null,
    mention_count: roles.length,
    article_count: options.articles ?? 1,
    mentions: roles.map(mention),
    merged: [],
  };
}

/** Un vínculo «aparecen juntas» sugerido entre dos personas `E<id>`. */
export function link(a: number, b: number, strength: LinkStrength): Relationship {
  const end = (id: number) => ({
    id,
    type: 'person',
    type_label: 'persona',
    label: `E${String(id)}`,
    legal_status: null,
    legal_status_label: null,
  });
  return {
    id: null,
    entity_a: end(a),
    entity_b: end(b),
    type: 'appears_with',
    type_label: 'aparecen juntas',
    custom_label: null,
    symmetric: true,
    origin: 'cooccurrence',
    origin_label: 'aparecen en la misma nota',
    confidence: 0.7,
    review_status: 'suggested',
    review_status_label: 'sugerido',
    reviewed_by: null,
    reviewed_at: null,
    notes: null,
    shared_articles: [],
    same_event_count: strength === 'strong' ? 1 : 0,
    strength,
    strength_label: strength === 'strong' ? 'relación fuerte' : 'solo se mencionan juntas',
    reason: strength === 'strong' ? 'participan en el mismo hecho en 1 nota' : 'x',
  };
}
