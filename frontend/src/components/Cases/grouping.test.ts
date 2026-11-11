import { describe, expect, it } from 'vitest';

import type { Entity, LegalStatus, Mention } from '../../services/entities';
import type { Relationship } from '../../services/relationships';
import {
  effectiveLegal,
  groupByType,
  participatesInEvent,
  relationshipKey,
  splitByStrength,
} from './grouping';

let nextMention = 1;

function mention(role: Mention['role']): Mention {
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

function entity(
  id: number,
  type: string,
  label: string,
  options: {
    roles?: Mention['role'][];
    legal?: LegalStatus | null;
    suggested?: LegalStatus | null;
    articles?: number;
  } = {},
): Entity {
  const roles = options.roles ?? ['mentioned'];
  return {
    id,
    type,
    type_label: type,
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

function link(a: number, b: number, strength: 'strong' | 'weak'): Relationship {
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
    reason: 'x',
  };
}

describe('grupos por tipo', () => {
  it('ordena los grupos: quién y con qué antes que dónde', () => {
    const groups = groupByType([
      entity(1, 'place', 'Culiacán'),
      entity(2, 'vehicle', 'camioneta Ford'),
      entity(3, 'org', 'FGR'),
      entity(4, 'person', 'Juan'),
      entity(5, 'weapon', 'rifle'),
    ]);

    expect(groups.map((g) => g.label)).toEqual([
      'Personas',
      'Organizaciones',
      'Vehículos',
      'Lugares',
      // Un tipo nuevo del backend no se pierde: va al final con su etiqueta.
      'weapon',
    ]);
  });

  it('dentro del grupo, primero quien participa en el hecho y luego por estatus legal', () => {
    const [people] = groupByType([
      entity(1, 'person', 'Ana', { suggested: 'victim' }),
      entity(2, 'person', 'Beto', { roles: ['event'], suggested: 'witness' }),
      entity(3, 'person', 'Carlos', { roles: ['mentioned', 'event'], legal: 'detained' }),
      // Sin estatus cuenta como «mencionado»: va después de la víctima.
      entity(4, 'person', 'Dora'),
      entity(5, 'person', 'Elsa', { suggested: 'victim', articles: 3 }),
    ]);

    expect(people?.items.map((e) => e.label)).toEqual(['Carlos', 'Beto', 'Elsa', 'Ana', 'Dora']);
    expect(people?.inEvent).toBe(2);
  });

  it('en lo que no es persona desempata por notas y luego por nombre', () => {
    const [orgs] = groupByType([
      entity(1, 'org', 'Marina'),
      entity(2, 'org', 'Ejército', { articles: 2 }),
      entity(3, 'org', 'Cártel'),
    ]);

    expect(orgs?.items.map((e) => e.label)).toEqual(['Ejército', 'Cártel', 'Marina']);
  });

  it('sin entidades no hay grupos', () => {
    expect(groupByType([])).toEqual([]);
  });
});

describe('papel y estatus de una entidad', () => {
  it('participa en el hecho si alguna mención lo dice', () => {
    expect(participatesInEvent(entity(1, 'person', 'A', { roles: ['mentioned', 'event'] }))).toBe(
      true,
    );
    expect(participatesInEvent(entity(1, 'person', 'A'))).toBe(false);
  });

  it('el estatus confirmado gana sobre el sugerido', () => {
    expect(effectiveLegal({ legal_status: 'charged', suggested_legal_status: 'alleged' })).toBe(
      'charged',
    );
    expect(effectiveLegal({ legal_status: null, suggested_legal_status: 'alleged' })).toBe(
      'alleged',
    );
    expect(effectiveLegal({ legal_status: null, suggested_legal_status: null })).toBeNull();
  });
});

describe('fuerza de los vínculos', () => {
  it('parte en fuertes y débiles sin cambiar el orden', () => {
    const { strong, weak } = splitByStrength([
      link(1, 2, 'strong'),
      link(1, 3, 'weak'),
      link(2, 3, 'strong'),
    ]);

    expect(strong.map(relationshipKey)).toEqual(['1-2-appears_with', '2-3-appears_with']);
    expect(weak.map(relationshipKey)).toEqual(['1-3-appears_with']);
  });
});
