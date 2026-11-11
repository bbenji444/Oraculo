/**
 * Entrar al monitor igual que a Oráculo, salir y saber quién soy (ADR-0043).
 *
 * Se entra en pasos: usuario y contraseña → (primer ingreso: cambiar la
 * temporal y dar de alta Microsoft Authenticator) → código de 6 dígitos. Cada
 * paso devuelve un `ticket` que se manda en el siguiente. El último deja la
 * cookie `HttpOnly` con el token interno; este código no la puede leer (así
 * un script malicioso tampoco) y la pantalla nunca guarda la contraseña.
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

/** Qué sigue en el ingreso. */
export type NextStep = 'code' | 'change_password' | 'enroll';

export interface LoginStep {
  ticket: string;
  next: NextStep;
}

/** Lo necesario para dar de alta Microsoft Authenticator. */
export interface Enrollment {
  qr_svg: string;
  secret: string;
  uri: string;
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

function isStep(value: unknown): value is LoginStep {
  const step = value as Partial<LoginStep> | null;
  return (
    typeof step?.ticket === 'string' &&
    (step.next === 'code' || step.next === 'change_password' || step.next === 'enroll')
  );
}

function meOf(data: unknown): Me {
  if (!isMe(data)) throw badFormat();
  return data;
}

function stepOf(data: unknown): LoginStep {
  if (!isStep(data)) throw badFormat();
  return data;
}

/** Quién soy; lanza `ApiError` con código `auth_required` si no hay sesión. */
export async function getMe(signal?: AbortSignal): Promise<Me> {
  return meOf(await requestJson(apiUrl('auth/me'), { signal }));
}

/** Paso 1: usuario y contraseña. */
export async function startLogin(username: string, password: string): Promise<LoginStep> {
  return stepOf(
    await requestJson(apiUrl('auth/login'), { method: 'POST', body: { username, password } }),
  );
}

/** Primer ingreso: cambiar la contraseña temporal. */
export async function setFirstPassword(ticket: string, newPassword: string): Promise<LoginStep> {
  return stepOf(
    await requestJson(apiUrl('auth/login/password'), {
      method: 'POST',
      body: { ticket, new_password: newPassword },
    }),
  );
}

/** Primer ingreso: pedir el QR de Microsoft Authenticator. */
export async function startEnrollment(ticket: string): Promise<Enrollment> {
  const data = (await requestJson(apiUrl('auth/login/enroll'), {
    method: 'POST',
    body: { ticket },
  })) as Partial<Enrollment> | null;
  if (typeof data?.qr_svg !== 'string' || typeof data.secret !== 'string') throw badFormat();
  return { qr_svg: data.qr_svg, secret: data.secret, uri: data.uri ?? '' };
}

/** Primer ingreso: el primer código confirma el celular y abre la sesión. */
export async function confirmEnrollment(ticket: string, code: string): Promise<Me> {
  return meOf(
    await requestJson(apiUrl('auth/login/enroll/confirm'), {
      method: 'POST',
      body: { ticket, code },
    }),
  );
}

/** Paso final: el código de 6 dígitos abre la sesión. */
export async function submitCode(ticket: string, code: string): Promise<Me> {
  return meOf(
    await requestJson(apiUrl('auth/login/code'), { method: 'POST', body: { ticket, code } }),
  );
}

/** Cambiar mi contraseña con la sesión abierta. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<Me> {
  return meOf(
    await requestJson(apiUrl('auth/password'), {
      method: 'POST',
      body: { current_password: currentPassword, new_password: newPassword },
    }),
  );
}

/** Cierra la sesión (y la API borra la cookie). */
export async function logout(): Promise<void> {
  await requestJson(apiUrl('auth/logout'), { method: 'POST' });
}

/** Un código de 6 dígitos bien escrito (se toleran espacios). */
export function looksLikeCode(text: string): boolean {
  return /^\d{6}$/.test(text.replace(/\s/g, ''));
}

/** La imagen del QR como `data:` (una imagen no puede ejecutar código). */
export function qrImageSrc(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
