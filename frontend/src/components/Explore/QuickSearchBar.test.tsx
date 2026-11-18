// @vitest-environment jsdom
/** Búsqueda rápida «como en Google» y «Guardar como concepto» (ADR-0110). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useExplorerStore } from '../../store/explorer';
import { useQuickSearchStore } from '../../store/quickSearch';
import { KeepQuickSearch, QuickSearchBar } from './QuickSearchBar';

const MEXICO = {
  id: 1,
  level: 'country',
  code: 'MEX',
  name: 'México',
  display_name: 'México',
  display_prefix: '',
  country_code: 'MEX',
  parent_id: null,
  point: { lon: -102, lat: 23 },
  bbox: [-118, 14, -86, 33],
  focus_bbox: [-118, 14, -86, 33],
  has_polygon: true,
  aliases: [],
};
const STARTED = {
  search_id: 'b01afb0d',
  status: 'pending',
  estimate: {},
  concept: { id: 41, name: 'Robo de vehículos' },
  suggestion_cost_usd: 0.0001,
  place_region: null,
};
const JALISCO = { id: 14, level: 'state', code: '14', name: 'Jalisco' };

/** Responde según la ruta: países, la búsqueda rápida o el concepto guardado. */
function stubApi(started: object = STARTED) {
  const spy = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) => {
    const body = url.includes('regions')
      ? { items: [MEXICO], next_cursor: null }
      : url.endsWith('/keep')
        ? { ...STARTED.concept, keywords: [], exclude_terms: [], color: '#00D2FF', is_active: true }
        : started;
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
  vi.stubGlobal('fetch', spy);
  return spy;
}

function renderWith(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  useExplorerStore.setState({ regionId: null, range: { kind: '7' }, searchId: null });
  useQuickSearchStore.setState({ last: null });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('QuickSearchBar', () => {
  it('busca lo que se escribió en México y abre la búsqueda', async () => {
    const spy = stubApi();
    renderWith(<QuickSearchBar providers={['google_news_rss']} busy={false} />);

    fireEvent.change(screen.getByLabelText('Busca noticias como en Google'), {
      target: { value: 'robo de autos con violencia en Jalisco' },
    });
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Búsqueda rápida' });
    await waitFor(() => {
      expect(button.disabled).toBe(false);
    });
    fireEvent.click(button);

    await waitFor(() => {
      expect(useExplorerStore.getState().searchId).toBe('b01afb0d');
    });
    const call = spy.mock.calls.find(([url]) => url.endsWith('searches/quick'));
    expect(JSON.parse(call?.[1]?.body as string)).toEqual({
      text: 'robo de autos con violencia en Jalisco',
      region_id: 1,
      days: 7,
      providers: ['google_news_rss'],
    });
    // Sin lugar en el texto se queda la región elegida (México).
    expect(useExplorerStore.getState().regionId).toBeNull();
    expect(useQuickSearchStore.getState().last).toMatchObject({ conceptId: 41, kept: false });
  });

  it('si el texto nombró un lugar, queda elegido en «Dónde»', async () => {
    stubApi({ ...STARTED, place_region: JALISCO });
    renderWith(<QuickSearchBar providers={undefined} busy={false} />);

    fireEvent.change(screen.getByLabelText('Busca noticias como en Google'), {
      target: { value: 'robo de autos con violencia en Jalisco' },
    });
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Búsqueda rápida' });
    await waitFor(() => {
      expect(button.disabled).toBe(false);
    });
    fireEvent.click(button);

    await waitFor(() => {
      expect(useExplorerStore.getState().searchId).toBe('b01afb0d');
    });
    expect(useExplorerStore.getState().regionId).toBe(14);
  });

  it('sin texto o con otra búsqueda corriendo no se puede buscar', () => {
    stubApi();
    renderWith(<QuickSearchBar providers={undefined} busy />);

    expect(
      screen.getByRole<HTMLButtonElement>('button', { name: 'Búsqueda rápida' }).disabled,
    ).toBe(true);
  });
});

describe('KeepQuickSearch', () => {
  it('solo sale en la búsqueda rápida y la guarda como concepto', async () => {
    const spy = stubApi();
    useQuickSearchStore.getState().remember({
      searchId: 'b01afb0d',
      conceptId: 41,
      conceptName: 'Robo de vehículos',
      text: 'robo de autos',
    });
    renderWith(
      <>
        <KeepQuickSearch searchId="otra" />
        <KeepQuickSearch searchId="b01afb0d" />
      </>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Guardar como concepto' }));

    expect(await screen.findByText('Guardado en Conceptos')).toBeTruthy();
    expect(spy.mock.calls.map(([url]) => url)).toContain('/api/v1/concepts/41/keep');
  });
});
