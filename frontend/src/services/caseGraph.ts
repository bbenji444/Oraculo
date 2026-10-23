/**
 * Servicio del muro de un caso y de «Mis casos» en el globo (Fase 9.6; docs/api.md).
 *
 * El servidor ya calcula dónde va cada nodo (§9.5: nunca en cada cuadro); aquí
 * solo se pide y se revisa la forma de la respuesta.
 *
 * No hace: no guarda estado (eso es TanStack Query en `hooks/useCaseGraph`).
 */
import { apiUrl } from '../config/api';
import type { LegalStatus } from './entities';
import { badFormat, requestJson } from './http';
import type { Relationship } from './relationships';
import { isRecord } from './searches';

/** Una entidad confirmada en el muro, con su posición ya calculada. */
export interface GraphNode {
  id: number;
  type: string;
  type_label: string;
  label: string;
  legal_status: LegalStatus | null;
  legal_status_label: string | null;
  mention_count: number;
  article_count: number;
  lon: number;
  lat: number;
  /** True: su propio punto (un lugar); false: junto al lugar de sus notas. */
  pinned: boolean;
  first_seen: string | null;
  last_seen: string | null;
}

/** Una nota del caso en la constelación. */
export interface GraphNote {
  article_id: number;
  title: string;
  url: string;
  published_at: string | null;
  lon: number;
  lat: number;
  entity_ids: number[];
}

export interface NoteLink {
  first: number;
  second: number;
  shared: number;
}

/** Lo que dibuja el globo de un caso. */
export interface CaseGraph {
  case_id: string;
  name: string;
  center: { lon: number; lat: number };
  /** Confirmadas que no caben en el tope («+N más»). */
  hidden_nodes: number;
  nodes: GraphNode[];
  edges: Relationship[];
  notes: GraphNote[];
  note_links: NoteLink[];
}

/** Un caso mío en el globo. */
export interface CaseOnMap {
  id: string;
  name: string;
  sensitivity: string;
  sensitivity_label: string;
  article_count: number;
  confirmed_count: number;
  lon: number;
  lat: number;
}

function isGraph(value: unknown): value is CaseGraph {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    isRecord(value.center) &&
    Array.isArray(value.nodes) &&
    Array.isArray(value.edges) &&
    Array.isArray(value.notes) &&
    Array.isArray(value.note_links)
  );
}

/** El muro de un caso (abrirlo queda en la bitácora como vista del caso). */
export async function getCaseGraph(caseId: string, signal?: AbortSignal): Promise<CaseGraph> {
  const data = await requestJson(apiUrl(`cases/${caseId}/graph`), { signal });
  if (!isGraph(data)) throw badFormat();
  return data;
}

/** Mis casos abiertos con al menos una nota ubicada. */
export async function listCasesOnMap(signal?: AbortSignal): Promise<CaseOnMap[]> {
  const data = await requestJson(apiUrl('cases/map'), { signal });
  if (!isRecord(data) || !Array.isArray(data.items)) throw badFormat();
  return data.items as CaseOnMap[];
}
