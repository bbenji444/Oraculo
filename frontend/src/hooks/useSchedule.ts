/**
 * Hooks del horario único de las corridas con TanStack Query (ADR-0040).
 *
 * Lo leen la pantalla «Envíos» y el Centro de mando (próxima corrida). Al
 * guardarlo se actualizan los dos.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getSchedule, saveSchedule, type ScheduleInput } from '../services/schedule';

const KEY = ['schedule'] as const;
// Las próximas corridas cambian con la hora: se vuelve a pedir cada minuto.
const REFRESH_MS = 60_000;

export function useSchedule() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) => getSchedule(signal),
    refetchInterval: REFRESH_MS,
  });
}

export function useSaveSchedule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ScheduleInput) => saveSchedule(input),
    onSuccess: (saved) => {
      client.setQueryData(KEY, saved);
    },
  });
}
