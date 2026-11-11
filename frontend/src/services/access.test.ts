// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { type AccessKey, createUser, issueKey, keyStatus, listUsers } from './access';
import { looksLikeCode, qrImageSrc, startLogin } from './auth';
import { ApiError, SESSION_EXPIRED_EVENT } from './http';

const KEY: AccessKey = {
  id: 1,
  user_id: 2,
  masked: 'orc_live_AbCd1234…',
  label: 'Laptop',
  created_by: 'benji',
  created_at: '2026-11-10T18:00:00Z',
  expires_at: null,
  revoked_at: null,
  last_used_at: null,
  last_used_ip: null,
};
const NOW = new Date('2026-11-10T19:00:00Z');

function reply(body: unknown, status = 200) {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('llaves', () => {
  it('distingue vigente, vencida y revocada', () => {
    expect(keyStatus(KEY, NOW)).toBe('vigente');
    expect(keyStatus({ ...KEY, expires_at: '2026-11-10T18:30:00Z' }, NOW)).toBe('vencida');
    expect(keyStatus({ ...KEY, revoked_at: '2026-11-10T18:10:00Z' }, NOW)).toBe('revocada');
  });

  it('la llave nueva llega completa una sola vez, con sus datos', async () => {
    const fetchMock = reply({ key: `orc_live_AbCd1234_${'a'.repeat(40)}`, info: KEY }, 201);
    vi.stubGlobal('fetch', fetchMock);

    const issued = await issueKey(2, 'Laptop', 90);

    expect(issued.key.startsWith('orc_live_')).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v1/access/users/2/keys');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ label: 'Laptop', days: 90 });
  });
});

describe('entrar', () => {
  it('reconoce un código de 6 dígitos (con o sin espacio)', () => {
    expect(looksLikeCode('123456')).toBe(true);
    expect(looksLikeCode('123 456')).toBe(true);
    expect(looksLikeCode('12345')).toBe(false);
    expect(looksLikeCode('abcdef')).toBe(false);
  });

  it('el QR se muestra como imagen data:, nunca como código incrustado', () => {
    const src = qrImageSrc('<svg><script>alert(1)</script></svg>');

    expect(src.startsWith('data:image/svg+xml;charset=utf-8,')).toBe(true);
    expect(src).not.toContain('<script>');
  });

  it('la contraseña viaja en el cuerpo, nunca en la URL', async () => {
    const fetchMock = reply({ ticket: 't', next: 'code' });
    vi.stubGlobal('fetch', fetchMock);

    const step = await startLogin('benji', 'Secreta-2026');

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(step).toEqual({ ticket: 't', next: 'code' });
    expect(url).toBe('/api/v1/auth/login');
    expect(url).not.toContain('Secreta');
    expect(JSON.parse(init.body as string)).toEqual({
      username: 'benji',
      password: 'Secreta-2026',
    });
  });

  it('el alta devuelve la contraseña temporal una sola vez', async () => {
    const user = {
      id: 3,
      username: 'ana',
      display_name: 'Ana',
      email: null,
      role: 'user',
      is_active: true,
      created_at: '2026-11-10T18:00:00Z',
      last_seen_at: null,
      active_keys: 0,
      has_password: true,
      must_change_password: true,
      totp_enrolled: false,
      locked_until: null,
    };
    vi.stubGlobal('fetch', reply({ user, temporary_password: 'Abcd2345Efgh6789' }, 201));

    const created = await createUser({
      username: 'ana',
      display_name: 'Ana',
      email: null,
      role: 'user',
    });

    expect(created.temporary_password).toBe('Abcd2345Efgh6789');
    expect(created.user.must_change_password).toBe(true);
  });
});

describe('sesión', () => {
  it('un 401 avisa que la sesión terminó', async () => {
    vi.stubGlobal(
      'fetch',
      reply({ error: { code: 'auth_required', message: 'Tu sesión terminó.' } }, 401),
    );
    const heard = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, heard);

    await expect(listUsers()).rejects.toBeInstanceOf(ApiError);

    expect(heard).toHaveBeenCalledOnce();
    window.removeEventListener(SESSION_EXPIRED_EVENT, heard);
  });

  it('un 403 no saca a nadie', async () => {
    vi.stubGlobal(
      'fetch',
      reply({ error: { code: 'forbidden', message: 'Solo superusuarios.' } }, 403),
    );
    const heard = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, heard);

    await expect(listUsers()).rejects.toThrow('Solo superusuarios.');

    expect(heard).not.toHaveBeenCalled();
    window.removeEventListener(SESSION_EXPIRED_EVENT, heard);
  });
});
