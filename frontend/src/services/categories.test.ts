/** Servicio de subdivisiones (`/api/v1/categories`, ADR-0038). */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { type Category, listCategories, updateCategory } from './categories';

const HOMICIDIO: Category = {
  id: 5,
  name: 'Homicidio',
  description: 'Asesinatos',
  is_other: false,
  color: '#FF4D6D',
  symbol: null,
  is_active: true,
  topic_concept_id: 21,
};

function respond(body: unknown, status = 200) {
  // Una respuesta nueva en cada llamada: el cuerpo de una se lee una sola vez.
  const spy = vi.fn<typeof fetch>(() =>
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

describe('listCategories', () => {
  it('pide las activas o, para el editor, también las apagadas', async () => {
    const spy = respond({ items: [HOMICIDIO] });

    expect(await listCategories()).toEqual([HOMICIDIO]);
    await listCategories(true);

    expect(spy.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/categories',
      '/api/v1/categories?include_inactive=true',
    ]);
  });

  it('rechaza una respuesta con otra forma', async () => {
    respond({ items: [{ id: 5, name: 'Homicidio' }] });

    await expect(listCategories()).rejects.toMatchObject({ code: 'bad_format' });
  });
});

describe('updateCategory', () => {
  it('manda solo lo que cambia con PATCH', async () => {
    const spy = respond({ ...HOMICIDIO, color: '#FF0000' });

    const saved = await updateCategory(5, { color: '#FF0000' });

    expect(saved.color).toBe('#FF0000');
    const [url, init] = spy.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/categories/5');
    expect(init?.method).toBe('PATCH');
    expect(JSON.parse(init?.body as string)).toEqual({ color: '#FF0000' });
  });
});
