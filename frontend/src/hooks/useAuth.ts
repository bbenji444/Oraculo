/**
 * La sesión de la persona con TanStack Query (ADR-0042).
 *
 * `useMe` dice quién entró: `null` si no hay sesión (la pantalla muestra
 * «Entrar»). Al entrar, salir o vencerse la sesión se **vacía toda la caché**:
 * en un equipo compartido, la siguiente persona no debe ver ni un dato de la
 * anterior.
 */
import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { type Me, getMe, login, logout } from '../services/auth';
import { ApiError, SESSION_EXPIRED_EVENT } from '../services/http';
import { useExplorerStore } from '../store/explorer';

const ME_KEY = ['auth', 'me'] as const;

/**
 * Cambia de persona (o a nadie) y borra todo lo demás de la caché.
 *
 * Primero se cambia `me` (la pantalla deja de mostrar el monitor) y después se
 * borra lo demás; `me` no se borra, solo se reemplaza, para que la pantalla
 * que lo observa se entere.
 */
function switchPerson(client: QueryClient, me: Me | null): void {
  client.setQueryData(ME_KEY, me);
  client.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] });
  // La búsqueda abierta en el globo era de la persona anterior.
  useExplorerStore.setState(useExplorerStore.getInitialState(), true);
}

async function meOrNull(signal?: AbortSignal): Promise<Me | null> {
  try {
    return await getMe(signal);
  } catch (error) {
    if (error instanceof ApiError && error.code === 'auth_required') return null;
    throw error;
  }
}

/** Quién soy (`null` sin sesión). Escucha cuando la API dice que la sesión terminó. */
export function useMe() {
  const client = useQueryClient();
  useEffect(() => {
    const onExpired = () => {
      // Un 401 de /auth/me sin sesión es lo normal: solo cuenta si había alguien.
      if (client.getQueryData(ME_KEY)) switchPerson(client, null);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
    };
  }, [client]);
  return useQuery({
    queryKey: ME_KEY,
    queryFn: ({ signal }) => meOrNull(signal),
    retry: false,
    staleTime: Infinity,
  });
}

/** Entrar con la llave. */
export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => login(key),
    onSuccess: (me) => {
      switchPerson(client, me);
    },
  });
}

/** Salir: cierra la sesión y olvida todo lo cargado. */
export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: logout,
    onSettled: () => {
      switchPerson(client, null);
    },
  });
}
