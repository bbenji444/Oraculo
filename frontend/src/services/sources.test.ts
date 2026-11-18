import { afterEach, describe, expect, it, vi } from 'vitest';

import { chosenSources, fetchSources, quickDefaultSources, type SourceOption } from './sources';

afterEach(() => {
  vi.unstubAllGlobals();
});

function respond(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  );
}

const OPTIONS: SourceOption[] = [
  {
    id: 'google_news_rss',
    label: 'Google News RSS',
    paid: false,
    configured: true,
    default_on: true,
  },
  { id: 'indice_local', label: 'Índice local', paid: false, configured: true, default_on: true },
  { id: 'searchapi', label: 'SearchApi', paid: true, configured: false, default_on: true },
];

describe('fuentes con las que se busca', () => {
  it('sin elegir: las de por defecto que estén configuradas', () => {
    expect(chosenSources(OPTIONS, null)).toEqual(['google_news_rss', 'indice_local']);
  });

  it('lo elegido manda, en el orden de pantalla y sin las no configuradas', () => {
    expect(chosenSources(OPTIONS, ['searchapi', 'indice_local'])).toEqual(['indice_local']);
  });

  it('con todo apagado no queda ninguna', () => {
    expect(chosenSources(OPTIONS, [])).toEqual([]);
  });
});

describe('fuentes de la búsqueda rápida sin elegir (ADR-0115)', () => {
  it('usa las de quick_default_on, solo entre las configuradas', () => {
    const options: SourceOption[] = [
      ...OPTIONS,
      {
        id: 'searchapi_web',
        label: 'Google web',
        paid: true,
        configured: true,
        default_on: false,
        quick_default_on: true,
      },
    ];
    expect(quickDefaultSources(options)).toEqual([
      'google_news_rss',
      'indice_local',
      'searchapi_web',
    ]);
  });

  it('un servidor viejo que no manda quick_default_on usa default_on', async () => {
    respond({ items: [{ ...OPTIONS[1] }] });
    const [item] = await fetchSources();
    expect(item?.quick_default_on).toBe(true);
  });
});

describe('créditos que le quedan a Google web (ADR-0115)', () => {
  const WEB = {
    id: 'searchapi_web',
    label: 'Google web',
    paid: true,
    configured: true,
    default_on: true,
  };

  it('si /sources dice cuántos quedan, se conservan', async () => {
    respond({ items: [{ ...WEB, credits_remaining: 46 }] });
    expect(await fetchSources()).toEqual([
      { ...WEB, quick_default_on: true, credits_remaining: 46 },
    ]);
  });

  it('si no viene o viene raro, la lista se lee igual y sin el número', async () => {
    respond({
      items: [
        WEB,
        { ...WEB, id: 'searchapi', credits_remaining: null },
        { ...WEB, id: 'otra', credits_remaining: '46' },
      ],
    });
    const items = await fetchSources();
    expect(items.map((o) => o.id)).toEqual(['searchapi_web', 'searchapi', 'otra']);
    expect(items.map((o) => o.credits_remaining ?? null)).toEqual([null, null, null]);
  });
});
