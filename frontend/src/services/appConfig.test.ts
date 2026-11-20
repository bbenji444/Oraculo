/** Configuración pública y el botón de regreso a Oráculo (09/11/2026). */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getAppConfig, safeOraculoUrl } from './appConfig';

describe('safeOraculoUrl', () => {
  it('acepta direcciones http y https', () => {
    expect(safeOraculoUrl('http://172.25.18.234')).toBe('http://172.25.18.234/');
    expect(safeOraculoUrl('https://oraculo.ejemplo.mx/inicio')).toBe(
      'https://oraculo.ejemplo.mx/inicio',
    );
  });

  it('sin dirección o con una peligrosa, no hay botón', () => {
    expect(safeOraculoUrl(null)).toBeNull();
    expect(safeOraculoUrl('')).toBeNull();
    expect(safeOraculoUrl('javascript:alert(1)')).toBeNull();
    expect(safeOraculoUrl('no es una dirección')).toBeNull();
  });
});

describe('getAppConfig', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const serve = (body: unknown) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }),
        ),
      ),
    );
  };

  it('dice si se entró por el gateway de Oráculo (ADR-0119)', async () => {
    serve({ oraculo_url: null, via_gateway: true });

    expect(await getAppConfig()).toEqual({ oraculo_url: null, via_gateway: true });
  });

  it('un servidor anterior sin via_gateway cuenta como acceso directo', async () => {
    serve({ oraculo_url: 'http://172.25.18.234' });

    expect(await getAppConfig()).toEqual({
      oraculo_url: 'http://172.25.18.234',
      via_gateway: false,
    });
  });

  it('rechaza un via_gateway que no es sí o no', async () => {
    serve({ oraculo_url: null, via_gateway: 'si' });

    await expect(getAppConfig()).rejects.toThrow();
  });
});
