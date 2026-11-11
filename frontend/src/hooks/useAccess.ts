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
  deleteUser,
  getAuthSettings,
  newApiKey,
  saveAuthSettings,
  showApiKey,
  issueKey,
  listKeys,
  listUsers,
  resetPassword,
  resetTotp,
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

export function useDeleteUser() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (id: number) => deleteUser(id), onSuccess: refresh });
}

export function useResetPassword() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (id: number) => resetPassword(id), onSuccess: refresh });
}

export function useResetTotp() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (id: number) => resetTotp(id), onSuccess: refresh });
}

export function useRevokeKey() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (keyId: number) => revokeKey(keyId), onSuccess: refresh });
}

const SETTINGS_KEY = ['access', 'settings'] as const;

/** Si al entrar se pide el código (ADR-0047). */
export function useAuthSettings() {
  return useQuery({ queryKey: SETTINGS_KEY, queryFn: ({ signal }) => getAuthSettings(signal) });
}

export function useSaveAuthSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (totpRequired: boolean) => saveAuthSettings({ totp_required: totpRequired }),
    onSuccess: (settings) => {
      client.setQueryData(SETTINGS_KEY, settings);
    },
  });
}

/** Trae la llave de API completa (no se guarda en la caché: cada vista queda en la bitácora). */
export function useShowApiKey() {
  return useMutation({ mutationFn: (userId: number) => showApiKey(userId) });
}

export function useNewApiKey() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: (userId: number) => newApiKey(userId), onSuccess: refresh });
}
