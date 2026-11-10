// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { type AccessKey, issueKey, keyStatus, listUsers } from './access';
import { looksLikeKey } from './auth';
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

  it('reconoce la forma de una llave antes de mandarla', () => {
    expect(looksLikeKey(`  orc_live_AbCd1234_${'a'.repeat(40)}\n`)).toBe(true);
    expect(looksLikeKey('sk-proj-123')).toBe(false);
    expect(looksLikeKey(`orc_live_AbCd1234_${'a'.repeat(39)}`)).toBe(false);
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
