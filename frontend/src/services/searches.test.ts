import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './http';
import {
  type Article,
  articleParams,
  estimateSearch,
  getAggregates,
  getArticle,
  getSearch,
  isFinished,
  isSettled,
  listAllArticles,
  listSearches,
  type Search,
  searchNotices,
  startQuickSearch,
  startSearch,
} from './searches';

function respondSequence(...bodies: { body: unknown; status?: number }[]) {
  const spy = vi.fn();
  for (const { body, status = 200 } of bodies) {
    spy.mockResolvedValueOnce(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  }
  vi.stubGlobal('fetch', spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const SEARCH: Search = {
  search_id: 'b01afb0d',
  status: 'running',
  region_id: 272,
  region_code: '14',
  region_name: 'Jalisco',
  date_from: '2026-10-10',
  date_to: '2026-10-17',
  concepts: [{ id: 3, name: 'Extorsión' }],
  progress: { stage: 'enrich', articles: 18, enriched: 10 },
  queries_planned: 2,
  credits_estimated: 1,
  credits_used: 1,
  llm_tokens_in: 0,
  llm_tokens_out: 0,
  llm_cost_usd: 0,
  results_count: 0,
  error_summary: null,
  created_at: '2026-10-17T09:00:48-06:00',
  started_at: null,
  finished_at: null,
};

function article(id: number): Article {
  return {
    article_id: id,
    title: `Nota ${String(id)}`,
    source_name: null,
    source_domain: 'informador.mx',
    url: 'https://informador.mx/a',
    published_at: null,
    summary: 'Resumen.',
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts: [],
    primary_location: null,
    in_region: null,
    providers: ['searchapi'],
  };
}

describe('servicio de búsquedas', () => {
  it('estima sin gastar con el cuerpo pedido', async () => {
    const spy = respondSequence({
      body: { queries: [], credits: 1, over_limit: false, llm: { model: 'gpt-6-luna' } },
    });

    const estimate = await estimateSearch({ concept_ids: [3], region_id: 272, days: 7 });

    expect(estimate.credits).toBe(1);
    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/searches/estimate');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ concept_ids: [3], region_id: 272, days: 7 });
  });

  it('lanza y devuelve el id; un 409 llega como ApiError en español', async () => {
    respondSequence(
      { body: { search_id: 'abc', status: 'pending' }, status: 202 },
      {
        body: {
          error: { code: 'credit_limit_reached', message: 'Pasaría el tope.', details: {} },
        },
        status: 409,
      },
    );

    expect(await startSearch({ concept_ids: [3], region_id: 272 })).toBe('abc');
    await expect(startSearch({ concept_ids: [3], region_id: 272 })).rejects.toMatchObject({
      code: 'credit_limit_reached',
      message: 'Pasaría el tope.',
    });
  });

  it('la búsqueda rápida trae el aviso de Google web si lo hubo (ADR-0115)', async () => {
    const started = {
      search_id: 'q1',
      status: 'pending',
      concept: { id: 41, name: 'Hacker Eternal' },
      place_region: null,
    };
    respondSequence(
      { body: { ...started, notice: 'Sin créditos de Google web: se buscó en noticias' } },
      { body: { ...started, notice: null } },
      // Respuestas de antes del aviso: sin el campo.
      { body: started },
    );
    const input = { text: 'hacker eternal', region_id: 1, days: 7 };

    expect((await startQuickSearch(input)).notice).toBe(
      'Sin créditos de Google web: se buscó en noticias',
    );
    expect((await startQuickSearch(input)).notice).toBeNull();
    expect((await startQuickSearch(input)).notice).toBeNull();
  });

  it('lee el avance y el historial', async () => {
    const spy = respondSequence({ body: SEARCH }, { body: { items: [SEARCH], next_cursor: 'c2' } });

    expect((await getSearch('b01afb0d')).progress.enriched).toBe(10);
    const page = await listSearches('c1');

    expect(page.next_cursor).toBe('c2');
    expect(spy.mock.calls[1]?.[0]).toBe('/api/v1/searches?limit=20&cursor=c1');
  });

  it('pide todas las notas siguiendo el cursor', async () => {
    const spy = respondSequence(
      { body: { items: [article(1), article(2)], next_cursor: 'x' } },
      { body: { items: [article(3)], next_cursor: null } },
    );

    const all = await listAllArticles('s1', { in_region: 'true' });

    expect(all.map((a) => a.article_id)).toEqual([1, 2, 3]);
    expect(spy.mock.calls[1]?.[0]).toBe(
      '/api/v1/searches/s1/articles?in_region=true&limit=200&cursor=x',
    );
  });

  it('arma los filtros de URL', () => {
    expect(
      articleParams({
        relevant: 'all',
        in_region: 'none',
        precision: ['state', 'country'],
        concept_id: 3,
      }).toString(),
    ).toBe('relevant=all&in_region=none&precision=state&precision=country&concept_id=3');
    expect(articleParams({}).toString()).toBe('');
  });

  it('mapa de calor y detalle de nota', async () => {
    respondSequence(
      { body: { level: 'state', items: [], coarser: 0, abroad: 0, unlocated: 2, total: 14 } },
      { body: { ...article(11), locations: [], first_seen_at: 'x', llm_model: null } },
    );

    expect((await getAggregates('s1', 'state')).total).toBe(14);
    expect((await getArticle(11)).locations).toEqual([]);
  });

  it('una respuesta con otra forma es un error claro', async () => {
    respondSequence({ body: { hola: 1 } }, { body: { items: [{ id: 1 }], next_cursor: null } });

    await expect(getSearch('x')).rejects.toBeInstanceOf(ApiError);
    await expect(listAllArticles('x', {})).rejects.toMatchObject({ code: 'bad_format' });
  });

  it('una cancelada se sigue leyendo hasta que el worker guarda lo gastado', () => {
    expect(isSettled({ status: 'cancelled', finished_at: null })).toBe(false);
    expect(isSettled({ status: 'cancelled', finished_at: '2026-11-19T17:19:20Z' })).toBe(true);
    expect(isSettled({ status: 'completed', finished_at: '2026-11-19T17:19:20Z' })).toBe(true);
    expect(isSettled({ status: 'running', finished_at: null })).toBe(false);
  });

  it('sabe cuándo terminó una búsqueda', () => {
    expect(isFinished('running')).toBe(false);
    expect(isFinished('pending')).toBe(false);
    expect(
      ['completed', 'partial', 'failed', 'cancelled'].every((s) =>
        isFinished(s as Search['status']),
      ),
    ).toBe(true);
  });

  it('junta los avisos de Google web: el del lanzamiento y el del worker, sin repetir', () => {
    const NO_CREDITS = 'Sin créditos de Google web: se buscó en noticias';
    const ACCOUNT = 'Google web no respondió (la cuenta de SearchApi): se buscó sin él';
    const launched = { searchId: SEARCH.search_id, notice: NO_CREDITS };

    expect(searchNotices(SEARCH, null)).toEqual([]);
    expect(searchNotices(SEARCH, launched)).toEqual([NO_CREDITS]);
    // El del lanzamiento solo vale para su búsqueda.
    expect(searchNotices(SEARCH, { searchId: 'otra', notice: NO_CREDITS })).toEqual([]);
    const withWorker = { ...SEARCH, progress: { ...SEARCH.progress, notice: ACCOUNT } };
    expect(searchNotices(withWorker, null)).toEqual([ACCOUNT]);
    expect(searchNotices(withWorker, launched)).toEqual([NO_CREDITS, ACCOUNT]);
    // El mismo texto por los dos lados sale una vez; los vacíos no salen.
    const same = { ...SEARCH, progress: { ...SEARCH.progress, notice: NO_CREDITS } };
    expect(searchNotices(same, launched)).toEqual([NO_CREDITS]);
    const blank = { ...SEARCH, progress: { ...SEARCH.progress, notice: '  ' } };
    expect(searchNotices(blank, { searchId: SEARCH.search_id, notice: null })).toEqual([]);
  });
});
