import { afterEach, describe, expect, it, vi } from 'vitest';

import { getIndexStats, searchLocalIndex, sourceLabel } from './localIndex';

function respond(body: unknown) {
  const spy = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('searchLocalIndex', () => {
  it('pide el concepto, la región y los días', async () => {
    const spy = respond({ notes: [], total: 0, by_day: [], by_source: [] });

    await searchLocalIndex({ conceptId: 1, regionId: 3, days: 7 });

    expect(spy.mock.calls[0]?.[0]).toBe(
      '/api/v1/local-index/search?concept_id=1&region_id=3&days=7',
    );
  });

  it('rechaza una respuesta con otra forma', async () => {
    respond({ notas: [] });

    await expect(searchLocalIndex({ conceptId: 1, regionId: 3, days: 7 })).rejects.toThrow();
  });
});

describe('getIndexStats', () => {
  it('trae el resumen', async () => {
    respond({ sources: [], total_notes: 0, total_mb: 0, last_run_at: null });

    await expect(getIndexStats()).resolves.toMatchObject({ total_notes: 0 });
  });

  it('rechaza una respuesta con otra forma', async () => {
    respond({});

    await expect(getIndexStats()).rejects.toThrow();
  });
});

describe('sourceLabel', () => {
  it('traduce las fuentes conocidas y los RSS', () => {
    expect(sourceLabel('gdelt_ngrams')).toBe('GDELT (texto completo)');
    expect(sourceLabel('rss:la-jornada')).toBe('RSS · la-jornada');
    expect(sourceLabel('otra')).toBe('otra');
  });
});
