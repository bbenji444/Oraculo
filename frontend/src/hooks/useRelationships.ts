/**
 * Hooks de los vínculos de un caso con TanStack Query (Fase 9.5).
 *
 * Revisar o dibujar un vínculo solo cambia los vínculos; lo que cambia las
 * entidades (confirmar, unir) los invalida desde `caseKeys`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { ReviewStatus } from '../services/entities';
import {
  createRelationship,
  listRelationships,
  type Relationship,
  type RelationshipDraft,
  reviewRelationship,
} from '../services/relationships';
import { relationshipsKey } from './caseKeys';

/** Vínculos del caso en un estado. */
export function useCaseRelationships(caseId: string, status: ReviewStatus) {
  return useQuery({
    queryKey: [...relationshipsKey(caseId), status],
    queryFn: ({ signal }) => listRelationships(caseId, status, signal),
  });
}

function useInvalidate(caseId: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: relationshipsKey(caseId) });
}

/** Confirmar o descartar un vínculo. */
export function useReviewRelationship(caseId: string) {
  const invalidate = useInvalidate(caseId);
  return useMutation({
    mutationFn: (input: { relationship: Relationship; action: 'confirm' | 'discard' }) =>
      reviewRelationship(caseId, input.relationship, input.action),
    onSuccess: invalidate,
  });
}

/** «Nuevo vínculo». */
export function useCreateRelationship(caseId: string) {
  const invalidate = useInvalidate(caseId);
  return useMutation({
    mutationFn: (draft: RelationshipDraft) => createRelationship(caseId, draft),
    onSuccess: invalidate,
  });
}
