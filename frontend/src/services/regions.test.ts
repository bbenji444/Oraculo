import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, getRegion, type Region, searchRegions } from './regions';

const iztapalapa: Region = {
  id: 3,
  level: 'municipality',
  code: '09007',
  name: 'Iztapalapa',
  display_name: 'Alcaldía Iztapalapa',
  display_prefix: 'Alcaldía',
  country_code: 'MEX',
  parent_id: 2,
  point: { lon: -99.05, lat: 19.34 },
  bbox: [-99.14, 19.28, -98.96, 19.4],
  has_polygon: true,
  aliases: [],
};

function respond(body: unknown, status = 200) {
  const spy = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
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

describe('searchRegions', () => {
  it('codifica el texto en la URL y devuelve las regiones', async () => {
    const spy = respond({ items: [iztapalapa] });

    await expect(searchRegions('peñón blanco')).resolves.toEqual([iztapalapa]);
    expect(spy).toHaveBeenCalledWith(
      '/api/v1/regions/search?q=pe%C3%B1%C3%B3n+blanco',
      expect.any(Object),
    );
  });

  it('entrega el mensaje en español del formato uniforme de error', async () => {
    respond(
      {
        error: {
          code: 'invalid_request',
          message: 'Escribe al menos 2 letras para buscar.',
          details: {},
        },
      },
      422,
    );

    await expect(searchRegions('a')).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Escribe al menos 2 letras para buscar.',
      code: 'invalid_request',
    });
  });

  it('rechaza un formato inesperado', async () => {
    respond({ items: [{ id: 'x' }] });

    await expect(searchRegions('izta')).rejects.toThrow('formato que no se reconoce');
  });

  it('falla con mensaje claro si no hay red', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );

    await expect(searchRegions('izta')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('getRegion', () => {
  it('devuelve el detalle con ancestros', async () => {
    const detail = {
      ...iztapalapa,
      ancestors: [{ id: 1, level: 'country', code: 'MEX', name: 'México' }],
      breadcrumb: 'México › Iztapalapa',
    };
    const spy = respond(detail);

    await expect(getRegion(3)).resolves.toEqual(detail);
    expect(spy).toHaveBeenCalledWith('/api/v1/regions/3', expect.any(Object));
  });

  it('región inexistente: error con código region_not_found', async () => {
    respond(
      { error: { code: 'region_not_found', message: 'No existe esa región.', details: {} } },
      404,
    );

    await expect(getRegion(999)).rejects.toMatchObject({ code: 'region_not_found' });
  });

  it('error sin cuerpo uniforme usa el código HTTP', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('<html>', { status: 502 }))),
    );

    await expect(getRegion(1)).rejects.toThrow('(502)');
  });
});
