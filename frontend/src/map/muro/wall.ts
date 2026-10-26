/**
 * Lo que dibuja el muro de un caso sobre el globo (Fase 9.6, plan §9.5).
 *
 * El motor (`engine.ts`) solo sabe de nodos con color y de arcos con
 * confianza; aquí se arma eso desde el grafo de la API (`wallFromGraph`) o
 * desde la constelación de notas (`constellationFromGraph`), con el realce del
 * nodo elegido (`focus`): él y sus vecinos se ven completos y lo demás se
 * atenúa.
 *
 * No hace: no dibuja ni pide datos.
 */
import type { CaseGraph, GraphNode } from '../../services/caseGraph';
import type { LegalStatus } from '../../services/entities';
import type { WallCase } from './types';

export type { WallCase, WallLink, WallNode } from './types';

/** Colores por tipo de entidad (plan §9.5: "color por tipo"). */
export const KIND_COLOR: Record<string, string> = {
  person: '#38BDF8',
  place: '#34D399',
  org: '#FBBF24',
  vehicle: '#A78BFA',
  note: '#F8FAFC',
};
const OTHER_KIND_COLOR = '#CBD5E1';

/** Borde por estatus legal (plan §9.5: "borde rojo = señalado, azul = víctima"). */
export const LEGAL_RING: Record<LegalStatus, string> = {
  mentioned: '#E2E8F0',
  alleged: '#F87171',
  detained: '#FB923C',
  charged: '#EF4444',
  victim: '#60A5FA',
  witness: '#A3E635',
  official: '#C4B5FD',
};
const NO_LEGAL_RING = '#E2E8F0';

// Realce al elegir un nodo: los demás se ven a esta intensidad.
export const DIM_FOCUS = 0.22;

/** Ids de los nodos unidos al elegido (incluido él). */
function neighborhood(graph: CaseGraph, selectedId: number | null): Set<number> | null {
  if (selectedId === null) return null;
  const near = new Set([selectedId]);
  for (const edge of graph.edges) {
    if (edge.entity_a.id === selectedId) near.add(edge.entity_b.id);
    if (edge.entity_b.id === selectedId) near.add(edge.entity_a.id);
  }
  return near;
}

function nodeColor(node: GraphNode): string {
  return KIND_COLOR[node.type] ?? OTHER_KIND_COLOR;
}

/**
 * El muro de entidades: nodos por entidad confirmada y arcos por vínculo.
 *
 * @example wallFromGraph(graph, null).nodes[0].focus // 1: nada elegido
 */
export function wallFromGraph(graph: CaseGraph, selectedId: number | null): WallCase {
  const near = neighborhood(graph, selectedId);
  const focusOf = (id: number) => (near === null || near.has(id) ? 1 : DIM_FOCUS);
  return {
    nodes: graph.nodes.map((node) => ({
      id: String(node.id),
      label: node.label,
      color: nodeColor(node),
      ring: node.legal_status ? LEGAL_RING[node.legal_status] : NO_LEGAL_RING,
      lng: node.lon,
      lat: node.lat,
      focus: focusOf(node.id),
      selected: node.id === selectedId,
    })),
    links: graph.edges.map((edge) => {
      const touches =
        selectedId === null || edge.entity_a.id === selectedId || edge.entity_b.id === selectedId;
      return {
        id: `${String(edge.entity_a.id)}-${String(edge.entity_b.id)}-${edge.type}`,
        from: String(edge.entity_a.id),
        to: String(edge.entity_b.id),
        confirmed: edge.review_status === 'confirmed',
        confidence: edge.confidence * (touches ? 1 : DIM_FOCUS),
      };
    }),
  };
}

// Las notas comparten la fuente de nodos con las entidades: un prefijo evita
// que el id de una nota choque con el de una entidad.
export const NOTE_PREFIX = 'nota-';

// Los títulos de las notas son largos: en el mapa se ve el principio y el
// completo sale al hacer clic (con más se enciman, medido con el caso real).
export const NOTE_LABEL_MAX_CHARS = 32;

/** El principio del título, cortado en una palabra. */
export function shortTitle(title: string): string {
  if (title.length <= NOTE_LABEL_MAX_CHARS) return title;
  const cut = title.slice(0, NOTE_LABEL_MAX_CHARS);
  const space = cut.lastIndexOf(' ');
  return `${(space > 0 ? cut.slice(0, space) : cut).trimEnd()}…`;
}

/** La constelación: las notas del caso como puntos de luz unidos por lo que comparten. */
export function constellationFromGraph(graph: CaseGraph): WallCase {
  const most = Math.max(1, ...graph.note_links.map((l) => l.shared));
  return {
    nodes: graph.notes.map((note) => ({
      id: `${NOTE_PREFIX}${String(note.article_id)}`,
      label: shortTitle(note.title),
      color: KIND_COLOR.note ?? OTHER_KIND_COLOR,
      ring: NO_LEGAL_RING,
      lng: note.lon,
      lat: note.lat,
      focus: 1,
      selected: false,
    })),
    links: graph.note_links.map((link) => ({
      id: `${String(link.first)}-${String(link.second)}`,
      from: `${NOTE_PREFIX}${String(link.first)}`,
      to: `${NOTE_PREFIX}${String(link.second)}`,
      confirmed: true,
      // Más entidades en común, arco más fuerte (de 0.35 a 1).
      confidence: 0.35 + (0.65 * link.shared) / most,
    })),
  };
}

/** Los extremos [oeste, sur, este, norte] de lo que se dibuja, para encuadrarlo. */
export function wallBounds(wall: WallCase): [number, number, number, number] | null {
  if (wall.nodes.length === 0) return null;
  const lngs = wall.nodes.map((n) => n.lng);
  const lats = wall.nodes.map((n) => n.lat);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}
