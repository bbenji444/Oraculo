// @vitest-environment jsdom
/** Búsqueda rápida «como en Google» y «Guardar como concepto» (ADR-0110). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useExplorerStore } from '../../store/explorer';
import { useQuickSearchStore } from '../../store/quickSearch';
import { KeepQuickSearch, QuickSearchBar } from './QuickSearchBar';
import { useSearchLauncher } from './useSearchLauncher';

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

  it('guarda el aviso del lanzamiento si Google web no alcanzó créditos (ADR-0115)', async () => {
    const NOTICE = 'Sin créditos de Google web: se buscó en noticias';
    stubApi({ ...STARTED, notice: NOTICE });
    renderWith(<QuickSearchBar providers={['google_news_rss', 'searchapi_web']} busy={false} />);

    fireEvent.change(screen.getByLabelText('Busca noticias como en Google'), {
      target: { value: 'hacker eternal' },
    });
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Búsqueda rápida' });
    await waitFor(() => {
      expect(button.disabled).toBe(false);
    });
    fireEvent.click(button);

    await waitFor(() => {
      expect(useQuickSearchStore.getState().last).toMatchObject({
        searchId: 'b01afb0d',
        notice: NOTICE,
      });
    });
  });

  it('al ajustar una búsqueda arranca con lo que se escribió (ADR-0118)', () => {
    stubApi();
    renderWith(
      <QuickSearchBar providers={['google_news_rss']} busy={false} initialText="hackeo a bases" />,
    );

    expect(screen.getByLabelText<HTMLInputElement>('Busca noticias como en Google').value).toBe(
      'hackeo a bases',
    );
  });

  it('sin texto o con otra búsqueda corriendo no se puede buscar', () => {
    stubApi();
    renderWith(<QuickSearchBar providers={undefined} busy />);

    expect(
      screen.getByRole<HTMLButtonElement>('button', { name: 'Búsqueda rápida' }).disabled,
    ).toBe(true);
  });
});

// /sources como lo manda el servidor cuando hay créditos de SearchApi: Google
// web va encendido solo en la búsqueda rápida (ADR-0115).
const SOURCES = {
  items: [
    {
      id: 'google_news_rss',
      label: 'Google News',
      paid: false,
      configured: true,
      default_on: true,
      quick_default_on: true,
    },
    {
      id: 'indice_local',
      label: 'Índice local',
      paid: false,
      configured: true,
      default_on: true,
      quick_default_on: true,
    },
    {
      id: 'searchapi',
      label: 'SearchApi',
      paid: true,
      configured: true,
      default_on: false,
      quick_default_on: false,
    },
    {
      id: 'searchapi_web',
      label: 'Google web',
      paid: true,
      configured: true,
      default_on: false,
      quick_default_on: true,
    },
  ],
};

/** La barra como la pone la consola: con las fuentes de `useSearchLauncher`. */
function LauncherBar() {
  const launcher = useSearchLauncher();
  return (
    <>
      <QuickSearchBar providers={launcher.quickProviders} busy={launcher.busy} />
      <output aria-label="Fuentes">{launcher.quickProviders?.join(',') ?? 'cargando'}</output>
      <output aria-label="Fuentes de la manual">
        {launcher.providers?.join(',') ?? 'cargando'}
      </output>
    </>
  );
}

/** Como `stubApi`, y además responde `/sources` y `/concepts`. */
function stubLauncherApi() {
  const spy = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) => {
    const body = url.includes('regions')
      ? { items: [MEXICO], next_cursor: null }
      : url.includes('sources')
        ? SOURCES
        : url.includes('concepts')
          ? { items: [], next_cursor: null }
          : STARTED;
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

async function launchQuick(spy: ReturnType<typeof stubLauncherApi>): Promise<unknown> {
  fireEvent.change(screen.getByLabelText('Busca noticias como en Google'), {
    target: { value: 'hacker eternal' },
  });
  const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Búsqueda rápida' });
  // Espera a que lleguen las fuentes: antes se mandaría sin `providers`.
  await waitFor(() => {
    expect(screen.getByLabelText('Fuentes').textContent).not.toBe('cargando');
    expect(button.disabled).toBe(false);
  });
  fireEvent.click(button);
  await waitFor(() => {
    expect(spy.mock.calls.some(([url]) => url.endsWith('searches/quick'))).toBe(true);
  });
  const call = spy.mock.calls.find(([url]) => url.endsWith('searches/quick'));
  return JSON.parse(call?.[1]?.body as string);
}

describe('fuentes de la búsqueda rápida (revisión del 18/11/2026)', () => {
  it('si el analista no tocó los switches, manda las de /sources, con Google web', async () => {
    useExplorerStore.setState({ sources: null });
    const spy = stubLauncherApi();
    renderWith(<LauncherBar />);

    expect(await launchQuick(spy)).toEqual({
      text: 'hacker eternal',
      region_id: 1,
      days: 7,
      providers: ['google_news_rss', 'indice_local', 'searchapi_web'],
    });
    // La manual no lo enciende sola: gasta un crédito por concepto.
    expect(screen.getByLabelText('Fuentes de la manual').textContent).toBe(
      'google_news_rss,indice_local',
    );
    // Debajo de la barra se dice que cuesta.
    expect(screen.getByText(/Incluye Google web/)).toBeTruthy();
  });

  it('si el analista eligió sus fuentes, se respetan', async () => {
    useExplorerStore.setState({ sources: null, sourcesChosen: false });
    useExplorerStore.getState().setSources(['google_news_rss']);
    const spy = stubLauncherApi();
    renderWith(<LauncherBar />);

    expect(await launchQuick(spy)).toMatchObject({ providers: ['google_news_rss'] });
    expect(screen.queryByText(/Incluye Google web/)).toBeNull();
    useExplorerStore.setState({ sources: null, sourcesChosen: false });
  });

  it('reabrir una búsqueda no borra lo que el analista ya eligió', async () => {
    // Revisión del 18/11/2026: apagó Google web y reabrió una búsqueda del
    // historial; la rápida debe seguir sin Google web.
    useExplorerStore.setState({ sources: null, sourcesChosen: false });
    useExplorerStore.getState().setSources(['google_news_rss', 'indice_local']);
    useExplorerStore.getState().restoreSearch({
      searchId: 'otra',
      regionId: 1,
      conceptIds: [13],
      dateFrom: '2026-11-01',
      dateTo: '2026-11-07',
      providers: ['google_news_rss'],
    });
    useExplorerStore.setState({ searchId: null, range: { kind: '7' } });
    const spy = stubLauncherApi();
    renderWith(<LauncherBar />);

    expect(await launchQuick(spy)).toMatchObject({ providers: ['google_news_rss'] });
    useExplorerStore.setState({ sources: null, sourcesChosen: false });
  });

  it('reabrir una búsqueda vieja no le quita Google web a la rápida', async () => {
    // Así estaba el navegador de Benji el 18/11/2026: las fuentes guardadas
    // venían de reabrir una búsqueda hecha antes de que existiera Google web,
    // sin que él tocara un switch.
    useExplorerStore.setState({ sources: null, sourcesChosen: false });
    useExplorerStore.getState().restoreSearch({
      searchId: 'vieja',
      regionId: 1,
      conceptIds: [13],
      dateFrom: '2026-11-01',
      dateTo: '2026-11-07',
      providers: ['google_news_rss', 'indice_local'],
    });
    useExplorerStore.setState({ searchId: null, range: { kind: '7' } });
    const spy = stubLauncherApi();
    renderWith(<LauncherBar />);

    expect(await launchQuick(spy)).toMatchObject({
      providers: ['google_news_rss', 'indice_local', 'searchapi_web'],
    });
    // La búsqueda manual («Ajustar consulta») sigue con las de la búsqueda reabierta.
    expect(useExplorerStore.getState().sources).toEqual(['google_news_rss', 'indice_local']);
    useExplorerStore.setState({ sources: null, sourcesChosen: false });
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
      notice: null,
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
