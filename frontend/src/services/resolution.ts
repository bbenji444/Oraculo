/**
 * Servicio de los duplicados de un caso (Fase 9.5, §9.8; docs/api.md).
 *
 * El sistema sugiere qué entidades del caso podrían ser la misma; aquí se
 * piden esas sugerencias y se mandan las decisiones de la persona: «Son la
 * misma», «No son la misma», «Separar» y «Separar menciones». Nada se une
 * solo (ADR-0104).
 *
 * No hace: no guarda estado (eso es TanStack Query en `hooks/useResolution`).
 */
import { apiUrl } from '../config/api';
import { asEntity, type Entity, isEntity } from './entities';
import { badFormat, requestJson } from './http';
import { isRecord } from './searches';

export type MergeReason = 'same_name' | 'shared_name' | 'similar_name';

/** Dos entidades del caso que podrían ser la misma, para verlas lado a lado. */
export interface MergeSuggestion {
  first: Entity;
  second: Entity;
  reason: MergeReason;
  reason_label: string;
  reasons: MergeReason[];
  /** Cuál se propone que quede: la confirmada; si no, la de más menciones. */
  keep_id: number;
}

function isSuggestion(value: unknown): value is MergeSuggestion {
  return (
    isRecord(value) &&
    isEntity(value.first) &&
    isEntity(value.second) &&
    typeof value.reason_label === 'string' &&
    typeof value.keep_id === 'number'
  );
}

/** Posibles duplicados del caso, los más seguros primero. */
export async function listMergeSuggestions(
  caseId: string,
  signal?: AbortSignal,
): Promise<MergeSuggestion[]> {
  const data = await requestJson(apiUrl(`cases/${caseId}/merge-suggestions`), { signal });
  if (!isRecord(data) || !Array.isArray(data.items) || !data.items.every(isSuggestion)) {
    throw badFormat();
  }
  return data.items;
}

/**
 * «Son la misma»: une `mergeId` a `keepId`. Responde la que queda.
 *
 * @throws {ApiError} `invalid_entity_merge` (tipos distintos, ya unida…),
 *   `case_forbidden` o `case_closed`.
 */
export async function mergeEntities(
  caseId: string,
  keepId: number,
  mergeId: number,
): Promise<Entity> {
  return asEntity(
    await requestJson(apiUrl('entities/merge'), {
      method: 'POST',
      body: { case_id: caseId, keep_id: keepId, merge_id: mergeId },
    }),
  );
}

/** «No son la misma»: el par deja de sugerirse. */
export async function dismissMerge(
  caseId: string,
  firstId: number,
  secondId: number,
): Promise<boolean> {
  const data = await requestJson(apiUrl('entities/merge/dismiss'), {
    method: 'POST',
    body: { case_id: caseId, first_id: firstId, second_id: secondId },
  });
  if (!isRecord(data) || typeof data.dismissed !== 'boolean') throw badFormat();
  return data.dismissed;
}

/** «Separar»: deshace una fusión. Responde la entidad separada. */
export async function unmergeEntity(caseId: string, entityId: number): Promise<Entity> {
  return asEntity(
    await requestJson(apiUrl(`entities/${String(entityId)}/unmerge`), {
      method: 'POST',
      body: { case_id: caseId },
    }),
  );
}

/** «Separar menciones»: pasan a una sugerencia nueva, que es lo que responde. */
export async function splitEntity(
  caseId: string,
  entityId: number,
  mentionIds: number[],
): Promise<Entity> {
  return asEntity(
    await requestJson(apiUrl(`entities/${String(entityId)}/split`), {
      method: 'POST',
      body: { case_id: caseId, mention_ids: mentionIds },
    }),
  );
}
