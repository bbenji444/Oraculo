import { describe, expect, it } from 'vitest';

import type { CaseGraph } from '../../services/caseGraph';
import type { Relationship } from '../../services/relationships';
import {
  constellationFromGraph,
  DIM_FOCUS,
  LEGAL_RING,
  shortTitle,
  wallBounds,
  wallFromGraph,
} from './wall';

function edge(a: number, b: number, status: 'suggested' | 'confirmed'): Relationship {
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
    review_status: status,
    review_status_label: status,
    reviewed_by: null,
    reviewed_at: null,
    notes: null,
    shared_articles: [],
  };
}

function node(id: number, legal: 'victim' | 'alleged' | null, lon: number) {
  return {
    id,
    type: 'person',
    type_label: 'persona',
    label: `E${String(id)}`,
    legal_status: legal,
    legal_status_label: null,
    mention_count: 1,
    article_count: 1,
    lon,
    lat: 19.4,
    pinned: false,
    first_seen: null,
    last_seen: null,
  };
}

const GRAPH: CaseGraph = {
  case_id: 'c',
  name: 'Caso',
  center: { lon: -99.2, lat: 19.4 },
  hidden_nodes: 0,
  nodes: [node(1, 'victim', -99.21), node(2, 'alleged', -99.2), node(3, null, -99.19)],
  edges: [edge(1, 2, 'confirmed'), edge(2, 3, 'suggested')],
  notes: [
    {
      article_id: 10,
      title: 'Nota 10',
      url: 'https://x.mx/10',
      published_at: null,
      lon: -99.2,
      lat: 19.4,
      entity_ids: [1, 2],
    },
    {
      article_id: 11,
      title: 'Nota 11',
      url: 'https://x.mx/11',
      published_at: null,
      lon: -99.21,
      lat: 19.41,
      entity_ids: [2],
    },
  ],
  note_links: [{ first: 10, second: 11, shared: 1 }],
};

describe('muro desde el grafo', () => {
  it('pinta el borde por estatus legal y los sugeridos punteados', () => {
    const wall = wallFromGraph(GRAPH, null);

    expect(wall.nodes.map((n) => n.ring)).toEqual([
      LEGAL_RING.victim,
      LEGAL_RING.alleged,
      '#E2E8F0',
    ]);
    expect(wall.links.map((l) => l.confirmed)).toEqual([true, false]);
    expect(wall.nodes.every((n) => n.focus === 1)).toBe(true);
  });

  it('al elegir un nodo, él y sus vecinos quedan completos y lo demás se atenúa', () => {
    const wall = wallFromGraph(GRAPH, 1);

    expect(wall.nodes.map((n) => [n.id, n.focus, n.selected])).toEqual([
      ['1', 1, true],
      ['2', 1, false],
      ['3', DIM_FOCUS, false],
    ]);
    expect(wall.links.map((l) => l.confidence)).toEqual([0.7, 0.7 * DIM_FOCUS]);
  });

  it('la constelación une notas y encuadra todo', () => {
    const sky = constellationFromGraph(GRAPH);

    expect(sky.nodes.map((n) => n.id)).toEqual(['nota-10', 'nota-11']);
    expect(sky.links).toEqual([
      { id: '10-11', from: 'nota-10', to: 'nota-11', confirmed: true, confidence: 1 },
    ]);
    expect(wallBounds(wallFromGraph(GRAPH, null))).toEqual([-99.21, 19.4, -99.19, 19.4]);
    expect(wallBounds({ nodes: [], links: [] })).toBeNull();
  });
});

describe('títulos de la constelación', () => {
  it('corta en una palabra y deja los cortos igual', () => {
    expect(shortTitle('Nota corta')).toBe('Nota corta');
    expect(shortTitle('Giran orden de aprehensión contra empresario por asesinato')).toBe(
      'Giran orden de aprehensión…',
    );
  });
});
