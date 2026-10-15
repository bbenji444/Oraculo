import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchHealth, HealthRequestError, type SystemHealth } from './health';

const healthy: SystemHealth = {
  status: 'ok',
  components: [
    { name: 'api', status: 'ok', detail: null, latency_ms: 0.1, info: { version: '0.0.0' } },
    { name: 'database', status: 'ok', detail: null, latency_ms: 4.2, info: { postgis: '3.6.4' } },
  ],
};

function mockFetch(impl: () => Promise<Response>) {
  const spy = vi.fn(impl);
  vi.stubGlobal('fetch', spy);
  return spy;
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchHealth', () => {
  it('pide /api/v1/health y devuelve el estado sano', async () => {
    const spy = mockFetch(() => Promise.resolve(jsonResponse(healthy, 200)));

    await expect(fetchHealth()).resolves.toEqual(healthy);
    expect(spy).toHaveBeenCalledWith('/api/v1/health', expect.any(Object));
  });

  it('acepta 503 porque el cuerpo trae el detalle de qué falló', async () => {
    const degraded: SystemHealth = {
      status: 'degraded',
      components: [
        {
          name: 'redis',
          status: 'error',
          detail: 'No se pudo conectar a Redis (ConnectionError).',
          latency_ms: 2.0,
          info: {},
        },
      ],
    };
    mockFetch(() => Promise.resolve(jsonResponse(degraded, 503)));

    await expect(fetchHealth()).resolves.toEqual(degraded);
  });

  it('falla con mensaje claro si la API no responde', async () => {
    mockFetch(() => Promise.reject(new TypeError('Failed to fetch')));

    await expect(fetchHealth()).rejects.toThrow(HealthRequestError);
    await expect(fetchHealth()).rejects.toThrow('No se pudo contactar a la API');
  });

  it('falla si el código HTTP no es 200 ni 503', async () => {
    mockFetch(() => Promise.resolve(new Response('Bad Gateway', { status: 502 })));

    await expect(fetchHealth()).rejects.toThrow('código inesperado (502)');
  });

  it('falla si el cuerpo no tiene la forma esperada', async () => {
    mockFetch(() => Promise.resolve(jsonResponse({ status: 'ok', components: [{}] }, 200)));

    await expect(fetchHealth()).rejects.toThrow('formato que no se reconoce');
  });

  it('falla si el cuerpo no es JSON', async () => {
    mockFetch(() => Promise.resolve(new Response('<html>', { status: 200 })));

    await expect(fetchHealth()).rejects.toThrow('formato que no se reconoce');
  });

  it('deja pasar la cancelación sin convertirla en error de la API', async () => {
    mockFetch(() => Promise.reject(new DOMException('Aborted', 'AbortError')));

    await expect(fetchHealth()).rejects.toMatchObject({ name: 'AbortError' });
  });
});
