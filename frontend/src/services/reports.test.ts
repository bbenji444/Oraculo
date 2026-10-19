import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './http';
import { fetchExport, fetchReport } from './reports';

afterEach(() => {
  vi.unstubAllGlobals();
});

function respond(response: Response) {
  const spy = vi.fn(() => Promise.resolve(response));
  vi.stubGlobal('fetch', spy);
  return spy;
}

describe('reportes y datos', () => {
  it('el reporte se pide con POST y trae el nombre que sugiere la API', async () => {
    const spy = respond(
      new Response('%PDF-1.7', {
        headers: {
          'Content-Type': 'application/pdf',
          'Content-Disposition': 'attachment; filename="reporte-extorsion-jalisco-2026-10-17.pdf"',
        },
      }),
    );

    const file = await fetchReport('b01a', 'pdf');

    expect(spy).toHaveBeenCalledWith('/api/v1/searches/b01a/report?format=pdf', {
      method: 'POST',
    });
    expect(file.filename).toBe('reporte-extorsion-jalisco-2026-10-17.pdf');
    expect(await file.blob.text()).toBe('%PDF-1.7');
  });

  it('los datos se piden con GET; sin Content-Disposition no hay nombre', async () => {
    const spy = respond(new Response('titulo,medio'));

    const file = await fetchExport('b01a', 'csv');

    expect(spy).toHaveBeenCalledWith('/api/v1/searches/b01a/export?format=csv', {
      method: 'GET',
    });
    expect(file.filename).toBeNull();
  });

  it('una búsqueda que corre responde con su error en español', async () => {
    respond(
      new Response(
        JSON.stringify({
          error: { code: 'search_not_finished', message: 'La búsqueda todavía no termina.' },
        }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    const error = await fetchReport('b01a', 'html').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('search_not_finished');
    expect((error as ApiError).message).toBe('La búsqueda todavía no termina.');
  });

  it('sin conexión', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('offline'))),
    );

    await expect(fetchExport('b01a', 'geojson')).rejects.toMatchObject({ code: 'network_error' });
  });
});
