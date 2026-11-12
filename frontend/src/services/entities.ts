/**
 * Servicio de las entidades de un caso (Fase 9.4, historia H9.2; docs/api.md).
 *
 * La IA propone personas, organizaciones, lugares y vehículos de cada nota
 * del caso; aquí se piden, se confirman (con estatus legal en personas) o se
 * descartan, una por una o en bloque (F12, ADR-0107). Las llaves de la IA
 * nunca llegan aquí: todo pasa por el backend.
 *
 * No hace: no guarda estado (eso es TanStack Query en `hooks/useEntities`).
 */
import { apiUrl } from '../config/api';
import { badFormat, requestJson } from './http';
import { isRecord } from './searches';

export type ReviewStatus = 'suggested' | 'confirmed' | 'discarded';
export type LegalStatus =
  'mentioned' | 'alleged' | 'detained' | 'charged' | 'victim' | 'witness' | 'official';

/** Una cita de la nota donde aparece la entidad. */
export interface Mention {
  id: number;
  /** Entidad dueña: la misma, o una que se le unió (9.5). Solo las propias se separan. */
  entity_id: number;
  article_id: number;
  article_title: string;
  article_url: string;
  source_name: string | null;
  published_at: string | null;
  mention_text: string;
  role: 'event' | 'mentioned';
  legal_status_hint: LegalStatus | null;
  legal_status_hint_label: string | null;
  confidence: number;
  evidence_span: string;
}

/** Una entidad que se unió a otra (9.5). */
export interface MergedEntity {
  id: number;
  label: string;
  merged_into: number;
}

/** Una entidad del caso con su evidencia. */
export interface Entity {
  id: number;
  type: string;
  type_label: string;
  label: string;
  aliases: string[];
  review_status: ReviewStatus;
  review_status_label: string;
  legal_status: LegalStatus | null;
  legal_status_label: string | null;
  suggested_legal_status: LegalStatus | null;
  suggested_legal_status_label: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  region_id: number | null;
  region_name: string | null;
  mention_count: number;
  article_count: number;
  mentions: Mention[];
  /** Entidades que se le unieron (9.5); se pueden separar. */
  merged: MergedEntity[];
}

/** En qué va la lectura de las notas del caso por la IA. */
export interface Analysis {
  articles: number;
  pending: number;
  queued: number;
  done: number;
  failed: number;
  skipped: number;
  title_snippet: number;
  cost_usd: number;
  estimated_pending_cost_usd: number;
}

export interface CaseEntities {
  analysis: Analysis;
  counts: Record<ReviewStatus, number>;
  items: Entity[];
}

export function isEntity(value: unknown): value is Entity {
  return (
    isRecord(value) &&
    typeof value.id === 'number' &&
    typeof value.label === 'string' &&
    typeof value.review_status === 'string' &&
    Array.isArray(value.mentions) &&
    Array.isArray(value.merged)
  );
}

function isCaseEntities(value: unknown): value is CaseEntities {
  return (
    isRecord(value) &&
    isRecord(value.analysis) &&
    isRecord(value.counts) &&
    Array.isArray(value.items) &&
    value.items.every(isEntity)
  );
}

export function asEntity(value: unknown): Entity {
  if (!isEntity(value)) throw badFormat();
  return value;
}

/** Entidades del caso en un estado, con conteos y avance de la IA. */
export async function listCaseEntities(
  caseId: string,
  status: ReviewStatus,
  signal?: AbortSignal,
): Promise<CaseEntities> {
  const data = await requestJson(`${apiUrl(`cases/${caseId}/entities`)}?status=${status}`, {
    signal,
  });
  if (!isCaseEntities(data)) throw badFormat();
  return data;
}

/** "Analizar pendientes": manda al worker las notas que faltan. */
export async function analyzePending(caseId: string): Promise<number> {
  const data = await requestJson(apiUrl(`cases/${caseId}/extract`), { method: 'POST' });
  if (!isRecord(data) || typeof data.queued !== 'number') throw badFormat();
  return data.queued;
}

/**
 * Confirma una entidad. Una persona exige su estatus legal según la nota.
 *
 * @throws {ApiError} `invalid_entity_review`, `case_forbidden` o `case_closed`.
 */
export async function confirmEntity(
  caseId: string,
  entityId: number,
  legalStatus: LegalStatus | null,
): Promise<Entity> {
  return asEntity(
    await requestJson(apiUrl(`entities/${String(entityId)}/confirm`), {
      method: 'POST',
      body: { case_id: caseId, legal_status: legalStatus },
    }),
  );
}

/** Descarta una entidad: deja de proponerse, sin borrarse. */
export async function discardEntity(caseId: string, entityId: number): Promise<Entity> {
  return asEntity(
    await requestJson(apiUrl(`entities/${String(entityId)}/discard`), {
      method: 'POST',
      body: { case_id: caseId },
    }),
  );
}

/** Confirmar o descartar en bloque (F12, ADR-0107). */
export type BulkAction = 'confirm' | 'discard';

/** Una entidad elegida para revisar en bloque. */
export interface EntityDecision {
  entity_id: number;
  /** Solo al confirmar personas: el estatus que se ve en su renglón. */
  legal_status: LegalStatus | null;
}

/** Cómo quedó una revisión en bloque. */
export interface BulkReviewResult {
  /** Cuántas cambiaron (cada una con su entrada en la bitácora). */
  changed: number;
  /** Cuántas ya estaban así. */
  unchanged: number;
}

/** Valida la respuesta de una revisión en bloque (entidades o vínculos). */
export function asBulkResult(value: unknown): BulkReviewResult {
  if (!isRecord(value) || typeof value.changed !== 'number' || typeof value.unchanged !== 'number')
    throw badFormat();
  return { changed: value.changed, unchanged: value.unchanged };
}

/**
 * Confirma o descarta varias entidades a la vez: todas o ninguna.
 *
 * @throws {ApiError} `entity_not_found` (alguna ya no está en el caso),
 *   `invalid_entity_review`, `invalid_bulk_review`, `case_forbidden` o `case_closed`.
 */
export async function reviewEntities(
  caseId: string,
  action: BulkAction,
  items: EntityDecision[],
): Promise<BulkReviewResult> {
  return asBulkResult(
    await requestJson(apiUrl(`cases/${caseId}/entities/review`), {
      method: 'POST',
      body: { action, items },
    }),
  );
}
