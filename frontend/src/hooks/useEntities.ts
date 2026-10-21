/**
 * Hooks de las entidades de un caso con TanStack Query (Fase 9.4).
 *
 * Las claves empiezan con `cases` para que cualquier cambio del caso las
 * invalide junto con el resto. Mientras haya notas en la cola del worker, la
 * lista se vuelve a pedir cada `POLL_MS` para que las sugerencias aparezcan
 * solas.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  analyzePending,
  confirmEntity,
  discardEntity,
  type LegalStatus,
  listCaseEntities,
  type ReviewStatus,
} from '../services/entities';

// Cada nota tarda unos segundos en la IA; 3 s muestra el avance sin cargar
// al servidor.
export const POLL_MS = 3000;

/** Entidades del caso en un estado; se actualiza sola mientras la IA lee. */
export function useCaseEntities(caseId: string, status: ReviewStatus) {
  return useQuery({
    queryKey: ['cases', 'entities', caseId, status],
    queryFn: ({ signal }) => listCaseEntities(caseId, status, signal),
    refetchInterval: (query) => ((query.state.data?.analysis.queued ?? 0) > 0 ? POLL_MS : false),
  });
}

function useInvalidate(caseId: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ['cases', 'entities', caseId] });
}

/** "Analizar pendientes". */
export function useAnalyzePending(caseId: string) {
  const invalidate = useInvalidate(caseId);
  return useMutation({ mutationFn: () => analyzePending(caseId), onSuccess: invalidate });
}

/** Confirmar o descartar una entidad. */
export function useReviewEntity(caseId: string) {
  const invalidate = useInvalidate(caseId);
  return useMutation({
    mutationFn: (input: {
      entityId: number;
      action: 'confirm' | 'discard';
      legal?: LegalStatus;
    }) =>
      input.action === 'confirm'
        ? confirmEntity(caseId, input.entityId, input.legal ?? null)
        : discardEntity(caseId, input.entityId),
    onSuccess: invalidate,
  });
}
