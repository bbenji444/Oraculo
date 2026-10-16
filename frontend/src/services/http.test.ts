import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, requestJson } from './http';

function respond(body: unknown, status = 200) {
  const spy = vi.fn(() =>
    Promise.resolve(
      status === 204
        ? new Response(null, { status })
        : new Response(JSON.stringify(body), {
            status,
            headers: { 'Content-Type': 'application/json' },
          }),
    ),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('requestJson', () => {
  it('envía el cuerpo como JSON con su método', async () => {
    const spy = respond({ id: 1 }, 201);

    await expect(requestJson('/api/v1/x', { method: 'POST', body: { a: 'ñ' } })).resolves.toEqual({
      id: 1,
    });
    expect(spy).toHaveBeenCalledWith(
      '/api/v1/x',
      expect.objectContaining({
        method: 'POST',
        body: '{"a":"ñ"}',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }) as unknown,
      }),
    );
  });

  it('un 204 devuelve null', async () => {
    respond(null, 204);

    await expect(requestJson('/api/v1/x', { method: 'DELETE' })).resolves.toBeNull();
  });

  it('conserva los detalles del error uniforme', async () => {
    respond(
      {
        error: {
          code: 'invalid_concept',
          message: 'El concepto tiene datos inválidos.',
          details: { problemas: [{ campo: 'color', mensaje: 'Formato #RRGGBB.' }] },
        },
      },
      422,
    );

    await expect(requestJson('/api/v1/x')).rejects.toMatchObject({
      code: 'invalid_concept',
      details: { problemas: [{ campo: 'color', mensaje: 'Formato #RRGGBB.' }] },
    });
  });

  it('sin conexión da un error claro', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );

    await expect(requestJson('/api/v1/x')).rejects.toEqual(
      new ApiError('No se pudo contactar a la API.', 'network_error'),
    );
  });
});
