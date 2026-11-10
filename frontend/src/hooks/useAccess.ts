/**
 * Personas y llaves de «Accesos» con TanStack Query (solo superusuarios).
 *
 * La llave recién creada no se guarda en la caché: solo vive en el estado
 * del aviso que la muestra una vez.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type NewUserInput,
  type UserPatch,
  createUser,
  issueKey,
  listKeys,
  listUsers,
  revokeKey,
  updateUser,
} from '../services/access';

const USERS_KEY = ['access', 'users'] as const;

export function useAccessUsers() {
  return useQuery({ queryKey: USERS_KEY, queryFn: ({ signal }) => listUsers(signal) });
}

export function useAccessKeys(userId: number | null) {
  return useQuery({
    queryKey: ['access', 'keys', userId],
    queryFn: ({ signal }) => listKeys(userId ?? 0, signal),
    enabled: userId !== null,
  });
}

function useRefresh() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ['access'] });
}

export function useCreateUser() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: NewUserInput) => createUser(input),
    onSuccess: refresh,
  });
}

export function useUpdateUser() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: UserPatch }) => updateUser(id, patch),
    onSuccess: refresh,
  });
}

export function useIssueKey() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ userId, label, days }: { userId: number; label: string; days: number | null }) =>
      issueKey(userId, label, days),
    onSuccess: refresh,
  });
}

export function useRevokeKey() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (keyId: number) => revokeKey(keyId), onSuccess: refresh });
}
