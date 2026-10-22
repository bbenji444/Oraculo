/**
 * Hooks de los duplicados de un caso con TanStack Query (Fase 9.5, §9.8).
 *
 * Cada decisión (unir, no son la misma, separar, separar menciones) vuelve a
 * pedir entidades, duplicados y vínculos del caso, porque las tres cosas
 * cambian juntas (`caseKeys`).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  dismissMerge,
  listMergeSuggestions,
  mergeEntities,
  splitEntity,
  unmergeEntity,
} from '../services/resolution';
import { invalidateCaseEntities, mergeSuggestionsKey } from './caseKeys';

/** Posibles duplicados del caso. */
export function useMergeSuggestions(caseId: string) {
  return useQuery({
    queryKey: mergeSuggestionsKey(caseId),
    queryFn: ({ signal }) => listMergeSuggestions(caseId, signal),
  });
}

/** Una decisión sobre duplicados. */
export type ResolutionAction =
  | { kind: 'merge'; keepId: number; mergeId: number }
  | { kind: 'dismiss'; firstId: number; secondId: number }
  | { kind: 'unmerge'; entityId: number }
  | { kind: 'split'; entityId: number; mentionIds: number[] };

async function run(caseId: string, action: ResolutionAction): Promise<unknown> {
  switch (action.kind) {
    case 'merge':
      return mergeEntities(caseId, action.keepId, action.mergeId);
    case 'dismiss':
      return dismissMerge(caseId, action.firstId, action.secondId);
    case 'unmerge':
      return unmergeEntity(caseId, action.entityId);
    case 'split':
      return splitEntity(caseId, action.entityId, action.mentionIds);
  }
}

/** Unir, «No son la misma», separar o separar menciones. */
export function useResolution(caseId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: ResolutionAction) => run(caseId, action),
    onSuccess: () => invalidateCaseEntities(client, caseId),
  });
}
