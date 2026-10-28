// @vitest-environment jsdom
/**
 * Prueba de humo del flujo principal (historia H1, criterio de F6).
 *
 * Recorre la app como lo haría un analista: Explorar → buscar "Jalisco" →
 * elegir Extorsión → ver el costo → Buscar → seguir el avance → ver las notas,
 * las gráficas y la ficha de una nota. Y reabrir esa búsqueda desde Historial.
 * La historia H9.1 (Fase 9.3): agregar notas a un caso desde su ficha y verlas
 * en la pestaña Casos.
 *
 * La API responde con respuestas reales grabadas de la base local
 * (src/test/fixtures/explorar/, búsqueda "Extorsión · Jalisco"): nunca hay red
 * ni se gastan créditos. El globo (MapLibre) y el fondo espacial (three.js)
 * necesitan WebGL, que jsdom no tiene: se reemplazan por un sustituto que
 * recibe las mismas notas y muestra la ficha de la elegida.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import type { Case } from './services/cases';
import type { Article, Search } from './services/searches';
import { useExplorerStore } from './store/explorer';
import { useTimelineStore } from './store/timeline';
import articles from './test/fixtures/explorar/articles.json';
import concepts from './test/fixtures/explorar/concepts.json';
import estimate from './test/fixtures/explorar/estimate.json';
import jalisco from './test/fixtures/explorar/region-jalisco.json';
import jaliscoChildren from './test/fixtures/explorar/regions-jalisco-children.json';
import regionsSearch from './test/fixtures/explorar/regions-search.json';
import states from './test/fixtures/explorar/regions-states.json';
import search from './test/fixtures/explorar/search.json';

vi.mock('./components/Explore/ExploreGlobe', async () => {
  const { NewsCard } = await import('./components/Explore/NewsCard');
  const store = await import('./store/explorer');
  type Props = React.ComponentProps<
    typeof import('./components/Explore/ExploreGlobe').ExploreGlobe
  >;
  return {
    ExploreGlobe: ({ articles: notes, colors }: Props) => {
      const articleId = store.useExplorerStore((s) => s.articleId);
      const selected = notes.find((a) => a.article_id === articleId);
      return (
        <div data-testid="globo" data-notas={notes.length}>
          {selected && <NewsCard article={selected} colors={colors} />}
        </div>
      );
    },
  };
});
vi.mock('./components/Space/SpaceBackground', () => ({ SpaceBackground: () => null }));

const SEARCH_ID = search.search_id;
// Ruta de cada respuesta grabada (sin la base /api/v1 ni los parámetros).
const ROUTES: Record<string, unknown> = {
  concepts,
  'regions/search': regionsSearch,
  'regions/272': jalisco,
  regions: states,
  'regions/272/children': jaliscoChildren,
  'searches/estimate': estimate,
  [`searches/${SEARCH_ID}/articles`]: articles,
  searches: { items: [search], next_cursor: null },
};
// Mientras corre, la búsqueda va en la etapa de la IA (como la real a los ~30 s).
const RUNNING: Search = {
  ...(search as Search),
  status: 'running',
  progress: { ...search.progress, stage: 'enrich', enriched: 9 },
  finished_at: null,
};

let searchPolls = 0;
// Caso de la historia H9.1 y las notas que se le van agregando.
const CASE_ID = '2d6f9438-886a-444f-84e9-d47a146903c4';
const CASE: Case = {
  id: CASE_ID,
  name: 'Homicidio estilista Polanco',
  description: '',
  status: 'open',
  status_label: 'abierto',
  sensitivity: 'restricted',
  sensitivity_label: 'reservado',
  created_by: 'desarrollo',
  closed_at: null,
  created_at: '2026-10-21T16:40:42Z',
  updated_at: '2026-10-21T16:40:42Z',
  article_count: 0,
  role: 'owner',
  has_article: null,
};
const caseArticles: number[] = [];
const reportRequests: string[] = [];
const startBodies: unknown[] = [];

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// requestJson (services/http.ts) siempre llama a fetch con la URL como texto
// y el cuerpo ya convertido a JSON.
function fakeApi(input: string, init?: RequestInit): Promise<Response> {
  const url = new URL(input, 'http://localhost');
  const path = url.pathname.replace('/api/v1/', '');
  if (path === 'searches' && init?.method === 'POST') {
    startBodies.push(typeof init.body === 'string' ? JSON.parse(init.body) : init.body);
    return Promise.resolve(respond({ search_id: SEARCH_ID }, 202));
  }
  if (path === `searches/${SEARCH_ID}/report` && init?.method === 'POST') {
    reportRequests.push(url.search);
    return Promise.resolve(
      new Response('%PDF-1.7', {
        headers: {
          'Content-Type': 'application/pdf',
          'Content-Disposition': 'attachment; filename="reporte-extorsion-jalisco-2026-10-17.pdf"',
        },
      }),
    );
  }
  if (path.startsWith('cases')) return Promise.resolve(fakeCases(path, url, init));
  if (path === `searches/${SEARCH_ID}`) {
    // El primer sondeo la ve corriendo; los siguientes, terminada.
    searchPolls += 1;
    return Promise.resolve(respond(searchPolls === 1 ? RUNNING : search));
  }
  const body = ROUTES[path];
  if (body === undefined) return Promise.resolve(respond({ error: { message: path } }, 404));
  return Promise.resolve(respond(body));
}

function fakeCases(path: string, url: URL, init?: RequestInit): Response {
  const current = { ...CASE, article_count: caseArticles.length };
  if (path === 'cases') {
    const article = Number(url.searchParams.get('contains_article'));
    return respond({
      items: [{ ...current, has_article: article ? caseArticles.includes(article) : null }],
      next_cursor: null,
    });
  }
  if (path === `cases/${CASE_ID}/articles` && init?.method === 'POST') {
    // requestJson manda el cuerpo ya convertido a JSON (texto).
    const body = JSON.parse(init.body as string) as { article_id: number };
    const added = !caseArticles.includes(body.article_id);
    if (added) caseArticles.push(body.article_id);
    return respond({ article_id: body.article_id, added });
  }
  if (path === `cases/${CASE_ID}/articles`) {
    const items = (articles.items as Article[]).filter((a) => caseArticles.includes(a.article_id));
    return respond({ items, next_cursor: null });
  }
  if (path === `cases/${CASE_ID}`) return respond(current);
  return respond({ error: { message: path } }, 404);
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  // La lista de noticias empieza oculta: la reemplaza la línea del tiempo.
  useTimelineStore.setState({ listOpen: false });
  searchPolls = 0;
  caseArticles.length = 0;
  startBodies.length = 0;
  reportRequests.length = 0;
  window.location.hash = '#/explorar';
  useExplorerStore.setState(useExplorerStore.getInitialState(), true);
  vi.stubGlobal('fetch', vi.fn(fakeApi));
  // jsdom no implementa el desplazamiento; la lista lo usa al elegir una nota.
  Element.prototype.scrollIntoView = vi.fn();
  // Tampoco crea URLs de archivos en memoria; las descargas las usan.
  URL.createObjectURL = vi.fn(() => 'blob:prueba');
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// El avance se consulta cada 2 s (useSearch): las esperas dan margen a un sondeo.
const POLL_WAIT = { timeout: 5000 };

describe('flujo principal (H1, Centro de mando)', () => {
  it('armar la consulta en Jalisco, seguir el barrido y abrir una nota', async () => {
    renderApp();

    // 1. Región: «/» abre su tarjeta con el cursor en el buscador.
    expect(screen.getByRole('button', { name: /^Dónde: elige una región/ })).toBeTruthy();
    fireEvent.keyDown(window, { key: '/' });
    const where = screen.getByRole('dialog', { name: 'Ajustar la consulta: Dónde' });
    const finder = within(where).getByRole('combobox', {
      name: 'Buscar estado, municipio o localidad',
    });
    expect(document.activeElement).toBe(finder);
    fireEvent.change(finder, { target: { value: 'Jalisco' } });
    const suggestions = await within(where).findByRole('listbox');
    fireEvent.mouseDown(await within(suggestions).findByRole('option', { name: /^Jalisco/ }));
    expect(await screen.findByRole('button', { name: /^Dónde: Jalisco/ })).toBeTruthy();

    // 2. Concepto: su tarjeta, y Esc la cierra.
    fireEvent.click(screen.getByRole('button', { name: /^Qué rastrear: elige un concepto/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Extorsión' }));
    expect(await screen.findByRole('button', { name: /^Qué rastrear: Extorsión/ })).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();

    // 3. El costo se ve antes de gastar: 2 consultas y 1 crédito. Mientras la
    //    cifra corre, el número real queda para el lector de pantalla.
    const dock = screen.getByRole('region', { name: 'Centro de mando' });
    const figure = (label: string) => {
      const value = within(dock).getByText(label).nextElementSibling;
      if (!(value instanceof HTMLElement)) throw new Error(label);
      return value;
    };
    // La estimación llega del servidor un momento después.
    await within(dock).findByText('Consultas');
    expect(await within(figure('Consultas')).findByText('2')).toBeTruthy();
    expect(within(figure('Créditos')).getByText('1')).toBeTruthy();

    // 4. Lanzar: se envía lo elegido y la consola muestra el barrido por etapas.
    fireEvent.click(within(dock).getByRole('button', { name: 'Iniciar barrido ›' }));
    expect(await screen.findByText('Resumiendo y clasificando con la IA')).toBeTruthy();
    expect(screen.getByRole('listitem', { current: 'step' }).textContent).toBe('IA');
    expect(startBodies).toEqual([expect.objectContaining({ region_id: 272, concept_ids: [3] })]);

    // 5. Al terminar: letrero sobre el globo, renglón de la consulta y expediente.
    const dossier = await screen.findByRole(
      'complementary',
      { name: 'Expediente de la consulta' },
      POLL_WAIT,
    );
    expect(screen.getByRole('status').textContent).toContain('Búsqueda lista: 18 notas');
    expect(screen.getByRole('region', { name: 'Centro de mando' }).textContent).toContain(
      '18 notas',
    );
    // Elegir un hecho de la cronología abre su nota en el globo (Benji vio que
    // a veces no pasaba nada, 27/10/2026).
    const chronology = within(dossier).getByRole('region', { name: 'Cronología' });
    const [firstDay] = within(chronology).getAllByRole('list', { name: /^Hechos del/ });
    if (!firstDay) throw new Error('La cronología debería tener al menos un día.');
    const [firstFact] = within(firstDay).getAllByRole('button', { expanded: false });
    if (!firstFact) throw new Error('El día debería tener al menos un hecho.');
    fireEvent.click(firstFact);
    expect(await within(screen.getByTestId('globo')).findByRole('article')).toBeTruthy();

    // 6. «Noticias» cambia la cronología por la lista; globo y lista, las mismas.
    fireEvent.click(within(dossier).getByRole('button', { name: 'Noticias' }));
    const list = await within(dossier).findByRole('region', { name: 'Noticias' });
    const relevant = articles.items.filter((a) => a.concepts.some((c) => c.is_relevant));
    expect(within(list).getAllByRole('listitem')).toHaveLength(relevant.length);
    await waitFor(() => {
      expect(screen.getByTestId('globo').dataset.notas).toBe(String(relevant.length));
    });

    // 7. El resumen se pliega aparte para dar todo el alto a la lista; el PDF
    //    sigue a la mano junto a las pestañas.
    expect(within(dossier).getByText('Estados')).toBeTruthy();
    fireEvent.click(within(dossier).getByRole('button', { name: 'Plegar el resumen' }));
    expect(within(dossier).queryByText('Estados')).toBeNull();
    expect(within(dossier).getByRole('button', { name: 'Reporte (PDF)' })).toBeTruthy();
    expect(within(dossier).getByRole('region', { name: 'Noticias' })).toBe(list);
    fireEvent.click(within(dossier).getByRole('button', { name: 'Desplegar el resumen' }));

    // 8. Elegir una nota abre su ficha en el globo, con su link en otra pestaña.
    const note = relevant[0];
    if (!note) throw new Error('El fixture necesita al menos una nota relevante.');
    fireEvent.click(
      within(list).getByRole('button', { name: new RegExp(note.title.slice(0, 20)) }),
    );
    const card = await within(screen.getByTestId('globo')).findByRole('article');
    const original = within(card).getByRole('link', { name: /Ver nota original/ });
    expect(original.getAttribute('href')).toBe(note.url);
    expect(original.getAttribute('target')).toBe('_blank');

    // 9. Reporte en PDF desde el expediente.
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });
    fireEvent.click(within(dossier).getByRole('button', { name: 'Reporte (PDF)' }));
    await waitFor(() => {
      expect(saved).toEqual(['reporte-extorsion-jalisco-2026-10-17.pdf']);
    });

    // 10. «›» oculta el expediente y una pestaña en el borde lo regresa.
    fireEvent.click(within(dossier).getByRole('button', { name: 'Ocultar el expediente' }));
    expect(screen.queryByRole('complementary', { name: 'Expediente de la consulta' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Expediente ·/ }));
    expect(screen.getByRole('complementary', { name: 'Expediente de la consulta' })).toBeTruthy();
  }, 15000);

  it('reabrir una búsqueda del Historial no gasta nada', async () => {
    window.location.hash = '#/historial';
    renderApp();

    fireEvent.click(await screen.findByRole('button', { name: 'Abrir en el globo' }));

    expect(await screen.findByRole('region', { name: 'Cronología' }, POLL_WAIT)).toBeTruthy();
    // En el Centro de mando la lista va en una pestaña del expediente.
    fireEvent.click(screen.getByRole('button', { name: 'Noticias' }));
    expect(await screen.findByRole('region', { name: 'Noticias' })).toBeTruthy();
    expect(window.location.hash).toBe('#/explorar');
    expect(startBodies).toEqual([]);
    expect(useExplorerStore.getState()).toMatchObject({ regionId: 272, conceptIds: [3] });
  }, 15000);
});

describe('caso de investigación (H9.1)', () => {
  it('agregar notas al caso desde su ficha y verlas en la pestaña Casos', async () => {
    // La búsqueda ya terminó: el primer sondeo la ve lista.
    searchPolls = 1;
    const [first, second] = (articles.items as Article[]).filter((a) =>
      a.concepts.some((c) => c.is_relevant),
    );
    if (!first || !second) throw new Error('La grabación necesita dos notas relevantes.');
    useExplorerStore.setState({ searchId: SEARCH_ID, articleId: first.article_id });
    renderApp();

    // Primera nota: se elige el caso de la lista.
    fireEvent.click(await screen.findByRole('button', { name: '+ Agregar al caso' }, POLL_WAIT));
    fireEvent.click(await screen.findByRole('button', { name: /Homicidio estilista Polanco/ }));
    expect(await screen.findByText('Agregada a «Homicidio estilista Polanco».')).toBeTruthy();

    // Siguiente nota: el último caso usado queda a un clic.
    act(() => {
      useExplorerStore.getState().selectArticle(second.article_id);
    });
    fireEvent.click(
      await screen.findByRole('button', { name: '+ Agregar a «Homicidio estilista Polanco»' }),
    );
    await waitFor(() => {
      expect(caseArticles).toEqual([first.article_id, second.article_id]);
    });

    // En Casos: el caso con sus dos noticias.
    act(() => {
      window.location.hash = '#/casos';
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    fireEvent.click(await screen.findByRole('button', { name: /Homicidio estilista Polanco/ }));
    expect(await screen.findByText('Noticias del caso (2)')).toBeTruthy();
    // Explorar sigue montada (oculta) con las mismas notas: se buscan en Casos.
    const visible = (title: string) =>
      screen.getAllByText(title).filter((el) => !el.closest('[hidden]'));
    await waitFor(() => {
      expect(visible(first.title)).toHaveLength(1);
    });
    expect(visible(second.title)).toHaveLength(1);
  }, 15000);
});

describe('diseño de columna (?clasico, H1)', () => {
  // El diseño anterior se guarda por si se ocupa (Benji, 27/10/2026): con
  // `?clasico` en la URL, Explorar vuelve a la columna de la izquierda.
  beforeEach(() => {
    window.history.replaceState(null, '', '/?clasico#/explorar');
  });
  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('buscar en Jalisco, seguir el avance y abrir una nota', async () => {
    renderApp();

    // 1. Región: el buscador y los filtros quedan sincronizados.
    fireEvent.change(
      screen.getByRole('combobox', { name: 'Buscar estado, municipio o localidad' }),
      { target: { value: 'Jalisco' } },
    );
    // Sugerencias del buscador (los menús de estado solo abren su lista al hacer clic).
    const suggestions = await screen.findByRole('listbox');
    fireEvent.mouseDown(await within(suggestions).findByRole('option', { name: /^Jalisco/ }));
    const breadcrumbs = await screen.findByRole('navigation', { name: 'Región elegida' });
    expect(within(breadcrumbs).getByText('México')).toBeTruthy();
    await waitFor(() => {
      // El menú de estado (HudSelect) muestra el estado elegido.
      expect(screen.getByLabelText('Estado').textContent).toBe('Jalisco');
    });

    // 2. Concepto y estimación antes de gastar.
    fireEvent.click(await screen.findByRole('button', { name: 'Extorsión' }));
    expect(await screen.findByText(/2 consultas · hasta 1 crédito\(s\)/)).toBeTruthy();

    // 3. Buscar: se envía lo elegido y se ve el avance por etapas.
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
    expect(await screen.findByText('Resumiendo y clasificando con la IA')).toBeTruthy();
    // Mientras corre, todavía no hay descargas.
    expect(screen.queryByRole('button', { name: 'Reporte (PDF)' })).toBeNull();
    expect(startBodies).toEqual([expect.objectContaining({ region_id: 272, concept_ids: [3] })]);

    // 4. Al terminar: costo real, notas en el globo y lista (sin gráficas a la derecha).
    expect(await screen.findByText(/18 notas · 1 crédito\(s\)/, {}, POLL_WAIT)).toBeTruthy();
    // Un aviso dice que ya terminó (la persona pudo irse a otra pestaña).
    expect(screen.getByRole('status').textContent).toContain('Búsqueda lista: 18 notas');
    // La cronología reemplaza a la lista; «☰ Lista» la vuelve a mostrar.
    expect(await screen.findByRole('region', { name: 'Cronología' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '☰ Lista' }));
    const list = await screen.findByRole('region', { name: 'Noticias' });
    expect(screen.queryByText(/Top 5 estados/)).toBeNull();
    expect(screen.queryByText('Tipos de noticias')).toBeNull();

    // La búsqueda terminada se reduce a un renglón para dejarle espacio a la lista;
    // "Editar" la abre y "Listo" la vuelve a cerrar sin buscar de nuevo.
    const searchSection = screen.getByRole('region', { name: 'Búsqueda' });
    expect(within(searchSection).getByText('10 – 17 oct 2026', { exact: false })).toBeTruthy();
    // Las descargas van en el mismo renglón, no en un panel aparte.
    expect(
      within(searchSection)
        .getAllByRole('button')
        .map((b) => b.getAttribute('aria-label'))
        .filter(Boolean),
    ).toEqual(['Reporte (PDF)']);
    fireEvent.click(within(searchSection).getByRole('button', { name: 'Editar' }));
    expect(
      screen.getByRole('combobox', { name: 'Buscar estado, municipio o localidad' }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Listo' }));
    expect(screen.getByRole('button', { name: 'Editar' })).toBeTruthy();

    // "Ocultar" pliega solo la búsqueda: lo de abajo (aquí la lista) se queda a la vista.
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar ‹' }));
    expect(screen.queryByRole('region', { name: 'Búsqueda' })).toBeNull();
    expect(screen.getByRole('region', { name: 'Noticias' })).toBe(list);
    expect(useExplorerStore.getState().panelOpen).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar la búsqueda' }));
    expect(screen.getByRole('region', { name: 'Búsqueda' })).toBeTruthy();

    // Por defecto solo las relevantes, en la lista y en el globo por igual; la
    // pestaña "Fuera" las separa (§9 paso 7).
    const relevant = articles.items.filter((a) => a.concepts.some((c) => c.is_relevant));
    await waitFor(() => {
      expect(screen.getByTestId('globo').dataset.notas).toBe(String(relevant.length));
    });
    expect(within(list).getAllByRole('listitem')).toHaveLength(relevant.length);
    const outside = relevant.filter((a) => a.in_region === false).length;
    expect(within(list).getByRole('tab', { name: `Fuera · ${String(outside)}` })).toBeTruthy();

    // 5. Elegir una nota en la lista abre su ficha en el globo, con su link.
    const note = relevant[0];
    if (!note) throw new Error('El fixture necesita al menos una nota relevante.');
    fireEvent.click(
      within(list).getByRole('button', { name: new RegExp(note.title.slice(0, 20)) }),
    );
    const card = await within(screen.getByTestId('globo')).findByRole('article');
    const original = within(card).getByRole('link', { name: /Ver nota original/ });
    expect(original.getAttribute('href')).toBe(note.url);
    // Siempre en otra pestaña: el monitor no se pierde (pedido de Benji, 20/10/2026).
    expect(original.getAttribute('target')).toBe('_blank');
    expect(original.getAttribute('rel')).toContain('noopener');

    // 6. "No relevantes" muestra las descartadas en la lista y en el globo a la vez.
    const showIrrelevant = within(list).getByRole('checkbox', { name: 'No relevantes' });
    fireEvent.click(showIrrelevant);
    expect(within(list).getAllByRole('listitem')).toHaveLength(articles.items.length);
    expect(screen.getByTestId('globo').dataset.notas).toBe(String(articles.items.length));
    fireEvent.click(showIrrelevant);
    expect(screen.getByTestId('globo').dataset.notas).toBe(String(relevant.length));

    // 7. Reporte en PDF (H5): se pide con POST y se guarda con el nombre de la API.
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reporte (PDF)' }));
    await waitFor(() => {
      expect(saved).toEqual(['reporte-extorsion-jalisco-2026-10-17.pdf']);
    });
    expect(reportRequests).toEqual(['?format=pdf']);
  }, 15000);
});
