/**
 * Entrar con la llave de Oráculo, salir y saber quién soy (ADR-0042).
 *
 * La llave viaja una sola vez, en el cuerpo de `POST /auth/login`; la API
 * responde con una cookie `HttpOnly` que este código no puede leer (así un
 * script malicioso tampoco). La pantalla nunca guarda la llave.
 */
import { apiUrl } from '../config/api';
import { badFormat, requestJson } from './http';

export type Role = 'superuser' | 'user';

/** Pestañas que existen en la pantalla. */
export type Section =
  'explorar' | 'casos' | 'conceptos' | 'historial' | 'envios' | 'estado' | 'accesos';

/** La persona que entró. */
export interface Me {
  username: string;
  display_name: string;
  role: Role;
  sections: Section[];
  auth_mode: 'keys' | 'dev';
}

function isMe(value: unknown): value is Me {
  const me = value as Partial<Me> | null;
  return (
    typeof me?.username === 'string' &&
    typeof me.display_name === 'string' &&
    (me.role === 'superuser' || me.role === 'user') &&
    Array.isArray(me.sections) &&
    (me.auth_mode === 'keys' || me.auth_mode === 'dev')
  );
}

/** Quién soy; lanza `ApiError` con código `auth_required` si no hay sesión. */
export async function getMe(signal?: AbortSignal): Promise<Me> {
  const data = await requestJson(apiUrl('auth/me'), { signal });
  if (!isMe(data)) throw badFormat();
  return data;
}

/** Entra con la llave; la API deja la cookie de sesión. */
export async function login(key: string): Promise<Me> {
  const data = await requestJson(apiUrl('auth/login'), { method: 'POST', body: { key } });
  if (!isMe(data)) throw badFormat();
  return data;
}

/** Cierra la sesión (y la API borra la cookie). */
export async function logout(): Promise<void> {
  await requestJson(apiUrl('auth/logout'), { method: 'POST' });
}

/** Forma básica de una llave pegada, para avisar antes de mandarla. */
export function looksLikeKey(text: string): boolean {
  return /^orc_live_[A-Za-z0-9]{8}_[A-Za-z0-9]{40}$/.test(text.trim());
}
