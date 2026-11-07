/**
 * Hooks de envíos con TanStack Query (CLAUDE.md §6.2, ADR-0039).
 *
 * Cada cambio invalida lo necesario para que la pantalla se actualice sola.
 * El historial se refresca cada pocos segundos mientras haya envíos en curso
 * o esperando su reintento.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type AccountProvider,
  connectAccount,
  deleteRecipient,
  getDeliveryOverview,
  listAccounts,
  listDeliveries,
  listRecipients,
  listRules,
  type RecipientInput,
  refreshAccount,
  retryDelivery,
  type RuleInput,
  saveRecipient,
  saveRule,
  sendTest,
} from '../services/deliveries';

const KEY = ['deliveries'] as const;
// Mientras algo está por mandarse, el historial se vuelve a pedir cada 5 s.
const LIVE_REFRESH_MS = 5000;

export function useDeliveryOverview() {
  return useQuery({
    queryKey: [...KEY, 'overview'],
    queryFn: ({ signal }) => getDeliveryOverview(signal),
  });
}

export function useDeliveryAccounts() {
  return useQuery({
    queryKey: [...KEY, 'accounts'],
    queryFn: ({ signal }) => listAccounts(signal),
  });
}

export function useRecipients() {
  return useQuery({
    queryKey: [...KEY, 'recipients'],
    queryFn: ({ signal }) => listRecipients(signal),
  });
}

export function useRules() {
  return useQuery({ queryKey: [...KEY, 'rules'], queryFn: ({ signal }) => listRules(signal) });
}

export function useDeliveryHistory() {
  return useQuery({
    queryKey: [...KEY, 'history'],
    queryFn: ({ signal }) => listDeliveries(signal),
    refetchInterval: (query) =>
      query.state.data?.items.some((d) => d.status === 'pending' || d.status === 'sending')
        ? LIVE_REFRESH_MS
        : false,
  });
}

function useInvalidate(part: string) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: [...KEY, part] });
}

export function useConnectAccount() {
  const invalidate = useInvalidate('accounts');
  return useMutation({
    mutationFn: ({ provider, label }: { provider: AccountProvider; label: string }) =>
      connectAccount(provider, label),
    onSuccess: invalidate,
  });
}

export function useRefreshAccount() {
  const invalidate = useInvalidate('accounts');
  return useMutation({ mutationFn: (id: number) => refreshAccount(id), onSuccess: invalidate });
}

export function useSaveRecipient() {
  const invalidate = useInvalidate('recipients');
  return useMutation({
    mutationFn: ({ input, id }: { input: RecipientInput; id?: number }) => saveRecipient(input, id),
    onSuccess: invalidate,
  });
}

export function useSaveRule() {
  const invalidate = useInvalidate('rules');
  return useMutation({ mutationFn: (input: RuleInput) => saveRule(input), onSuccess: invalidate });
}

export function useDeleteRecipient() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteRecipient(id),
    // El historial muestra su nombre: se refresca todo.
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRetryDelivery() {
  const invalidate = useInvalidate('history');
  return useMutation({ mutationFn: (id: string) => retryDelivery(id), onSuccess: invalidate });
}

export function useSendTest() {
  const invalidate = useInvalidate('history');
  return useMutation({
    mutationFn: ({ recipientId, accountId }: { recipientId: number; accountId: number }) =>
      sendTest(recipientId, accountId),
    onSuccess: invalidate,
  });
}
