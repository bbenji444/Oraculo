/**
 * Servicio de los vínculos entre entidades de un caso (Fase 9.5; docs/api.md).
 *
 * «Aparecen juntas» lo sugiere el sistema cuando dos entidades confirmadas
 * comparten notas del caso; los demás los dibuja el analista y nacen
 * confirmados. Un sugerido todavía no tiene id: se revisa con su llave (las
 * dos entidades y el tipo).
 *
 * No hace: no guarda estado (eso es TanStack Query en `hooks/useRelationships`).
 */
import { apiUrl } from '../config/api';
import type { LegalStatus, ReviewStatus } from './entities';
import { badFormat, requestJson } from './http';
import { isRecord } from './searches';

export type RelationshipType =
  | 'appears_with'
  | 'same_event'
  | 'family'
  | 'associate'
  | 'employer'
  | 'located_in'
  | 'owns'
  | 'custom';

/** Una de las dos entidades del vínculo. */
export interface RelationshipEnd {
  id: number;
  type: string;
  type_label: string;
  label: string;
  legal_status: LegalStatus | null;
  legal_status_label: string | null;
}

/** Una nota del caso donde aparecen las dos entidades. */
export interface SharedArticle {
  article_id: number;
  title: string;
  url: string;
  published_at: string | null;
}

/** Un vínculo del caso con su origen, su confianza y su evidencia. */
export interface Relationship {
  /** Nulo si es una sugerencia que nadie ha revisado. */
  id: number | null;
  entity_a: RelationshipEnd;
  entity_b: RelationshipEnd;
  type: RelationshipType;
  type_label: string;
  custom_label: string | null;
  symmetric: boolean;
  origin: 'cooccurrence' | 'llm' | 'human';
  origin_label: string;
  confidence: number;
  review_status: ReviewStatus;
  review_status_label: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  notes: string | null;
  shared_articles: SharedArticle[];
}

export interface CaseRelationships {
  counts: Record<ReviewStatus, number>;
  items: Relationship[];
}

/** Lo que escribe el analista en «Nuevo vínculo». */
export interface RelationshipDraft {
  entityA: number;
  entityB: number;
  type: RelationshipType;
  customLabel: string;
  notes: string;
}

function isRelationship(value: unknown): value is Relationship {
  return (
    isRecord(value) &&
    isRecord(value.entity_a) &&
    isRecord(value.entity_b) &&
    typeof value.type === 'string' &&
    typeof value.confidence === 'number' &&
    Array.isArray(value.shared_articles)
  );
}

function asRelationship(value: unknown): Relationship {
  if (!isRelationship(value)) throw badFormat();
  return value;
}

/** Vínculos del caso en un estado, con conteos. */
export async function listRelationships(
  caseId: string,
  status: ReviewStatus,
  signal?: AbortSignal,
): Promise<CaseRelationships> {
  const data = await requestJson(`${apiUrl(`cases/${caseId}/relationships`)}?status=${status}`, {
    signal,
  });
  if (
    !isRecord(data) ||
    !isRecord(data.counts) ||
    !Array.isArray(data.items) ||
    !data.items.every(isRelationship)
  ) {
    throw badFormat();
  }
  return { counts: data.counts as Record<ReviewStatus, number>, items: data.items };
}

/**
 * Dibuja un vínculo (nace confirmado con la firma de quien lo crea).
 *
 * @throws {ApiError} `invalid_relationship` (entidad sin confirmar, falta la
 *   etiqueta de «otro»…), `case_forbidden` o `case_closed`.
 */
export async function createRelationship(
  caseId: string,
  draft: RelationshipDraft,
): Promise<Relationship> {
  return asRelationship(
    await requestJson(apiUrl('relationships'), {
      method: 'POST',
      body: {
        case_id: caseId,
        entity_a: draft.entityA,
        entity_b: draft.entityB,
        type: draft.type,
        custom_label: draft.type === 'custom' ? draft.customLabel : null,
        notes: draft.notes || null,
      },
    }),
  );
}

/** Confirma o descarta un vínculo con su llave (entidades y tipo). */
export async function reviewRelationship(
  caseId: string,
  relationship: Pick<Relationship, 'entity_a' | 'entity_b' | 'type'>,
  action: 'confirm' | 'discard',
): Promise<Relationship> {
  return asRelationship(
    await requestJson(apiUrl(`relationships/${action}`), {
      method: 'POST',
      body: {
        case_id: caseId,
        entity_a: relationship.entity_a.id,
        entity_b: relationship.entity_b.id,
        type: relationship.type,
      },
    }),
  );
}
