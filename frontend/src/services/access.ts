/**
 * Personas y llaves para la pantalla «Accesos» (solo superusuarios, ADR-0042).
 *
 * La llave completa llega una sola vez, en la respuesta de `issueKey`; la
 * pantalla la muestra para copiarla y no la guarda en ningún lado.
 */
import { apiUrl } from '../config/api';
import type { Role } from './auth';
import { badFormat, requestJson } from './http';

export interface AccessUser {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_seen_at: string | null;
  active_keys: number;
}

export interface AccessKey {
  id: number;
  user_id: number;
  masked: string;
  label: string;
  created_by: string;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  last_used_ip: string | null;
}

export interface NewUserInput {
  username: string;
  display_name: string;
  email: string | null;
  role: Role;
}

export interface UserPatch {
  display_name?: string;
  email?: string;
  role?: Role;
  is_active?: boolean;
}

export interface IssuedKey {
  key: string;
  info: AccessKey;
}

function isUser(value: unknown): value is AccessUser {
  const u = value as Partial<AccessUser> | null;
  return (
    typeof u?.id === 'number' &&
    typeof u.username === 'string' &&
    typeof u.display_name === 'string' &&
    (u.role === 'superuser' || u.role === 'user') &&
    typeof u.is_active === 'boolean' &&
    typeof u.active_keys === 'number'
  );
}

function isKey(value: unknown): value is AccessKey {
  const k = value as Partial<AccessKey> | null;
  return typeof k?.id === 'number' && typeof k.masked === 'string' && typeof k.label === 'string';
}

function itemsOf<T>(data: unknown, check: (v: unknown) => v is T): T[] {
  const items = (data as { items?: unknown } | null)?.items;
  if (!Array.isArray(items) || !items.every(check)) throw badFormat();
  return items;
}

export async function listUsers(signal?: AbortSignal): Promise<AccessUser[]> {
  return itemsOf(await requestJson(apiUrl('access/users'), { signal }), isUser);
}

export async function createUser(input: NewUserInput): Promise<AccessUser> {
  const data = await requestJson(apiUrl('access/users'), { method: 'POST', body: input });
  if (!isUser(data)) throw badFormat();
  return data;
}

export async function updateUser(id: number, patch: UserPatch): Promise<AccessUser> {
  const data = await requestJson(apiUrl(`access/users/${String(id)}`), {
    method: 'PATCH',
    body: patch,
  });
  if (!isUser(data)) throw badFormat();
  return data;
}

export async function listKeys(userId: number, signal?: AbortSignal): Promise<AccessKey[]> {
  return itemsOf(
    await requestJson(apiUrl(`access/users/${String(userId)}/keys`), { signal }),
    isKey,
  );
}

/** Crea una llave; `days` null = no vence. La llave completa solo viene aquí. */
export async function issueKey(
  userId: number,
  label: string,
  days: number | null,
): Promise<IssuedKey> {
  const data = await requestJson(apiUrl(`access/users/${String(userId)}/keys`), {
    method: 'POST',
    body: { label, days },
  });
  const issued = data as Partial<IssuedKey> | null;
  if (typeof issued?.key !== 'string' || !isKey(issued.info)) throw badFormat();
  return { key: issued.key, info: issued.info };
}

export async function revokeKey(keyId: number): Promise<AccessKey> {
  const data = await requestJson(apiUrl(`access/keys/${String(keyId)}`), { method: 'DELETE' });
  if (!isKey(data)) throw badFormat();
  return data;
}

/** Estado de una llave para mostrarlo. */
export function keyStatus(
  key: AccessKey,
  now: Date = new Date(),
): 'vigente' | 'revocada' | 'vencida' {
  if (key.revoked_at) return 'revocada';
  if (key.expires_at && new Date(key.expires_at) <= now) return 'vencida';
  return 'vigente';
}
