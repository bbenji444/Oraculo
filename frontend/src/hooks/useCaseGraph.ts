/**
 * Hooks del muro de un caso y de «Mis casos» con TanStack Query (Fase 9.6).
 *
 * Las claves empiezan con `cases` para que confirmar, unir o vincular
 * entidades (que invalidan `['cases', …]`) también refresque el muro.
 */
import { useQuery } from '@tanstack/react-query';

import { getCaseGraph, listCasesOnMap } from '../services/caseGraph';

/** El muro de un caso; nada si no hay caso abierto en el globo. */
export function useCaseGraph(caseId: string | null) {
  return useQuery({
    queryKey: ['cases', 'graph', caseId],
    queryFn: ({ signal }) => getCaseGraph(caseId ?? '', signal),
    enabled: caseId !== null,
  });
}

/** Mis casos en el globo, solo cuando el interruptor está encendido. */
export function useCasesOnMap(enabled: boolean) {
  return useQuery({
    queryKey: ['cases', 'map'],
    queryFn: ({ signal }) => listCasesOnMap(signal),
    enabled,
  });
}
