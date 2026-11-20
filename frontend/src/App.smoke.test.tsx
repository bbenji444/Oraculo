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
 * ni se gastan créditos. A las notas grabadas se sumaron tres hechas a mano
 * (ids 9001 a 9003: Facebook, YouTube y X, ADR-0117) para probar las
 * pestañas de plataforma y las bandas de relevancia (src/test/README.md). El globo (MapLibre) y el fondo espacial (three.js)
 * necesitan WebGL, que jsdom no tiene: se reemplazan por un sustituto que
 * recibe las mismas notas y muestra la ficha de la elegida.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import type { Me } from './services/auth';
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
// jsdom no tiene lienzo 2D: el fondo de constelación no se dibuja en las pruebas.
vi.mock('./components/Space/Constellation', () => ({ Constellation: () => null }));

const SEARCH_ID = search.search_id;
// Credenciales de la API falsa (no son reales).
const GOOD_PASSWORD = 'Contraseña-segura-2026';
const GOOD_CODE = '123456';
// Quién entró (ADR-0042): el superusuario, con todas las pestañas.
const BENJI: Me = {
  username: 'benji',
  display_name: 'Benjamin',
  role: 'superuser',
  sections: ['explorar', 'casos', 'conceptos', 'historial', 'envios', 'estado', 'accesos'],
  auth_mode: 'keys',
};
// Ruta de cada respuesta grabada (sin la base /api/v1 ni los parámetros).
const ROUTES: Record<string, unknown> = {
  concepts,
  'app-config': { oraculo_url: 'http://172.25.18.234' },
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
  if (path === 'auth/me') {
    return Promise.resolve(
      respond({ error: { code: 'auth_required', message: 'Entra con tu usuario.' } }, 401),
    );
  }
  if (path === 'auth/login' && init?.method === 'POST') {
    const body = JSON.parse(init.body as string) as { username: string; password: string };
    return Promise.resolve(
      body.username === 'benji' && body.password === GOOD_PASSWORD
        ? respond({ ticket: 'ingreso-1', next: 'code' })
        : respond(
            { error: { code: 'auth_required', message: 'Usuario o contraseña incorrectos.' } },
            401,
          ),
    );
  }
  if (path === 'auth/login/code' && init?.method === 'POST') {
    const body = JSON.parse(init.body as string) as { ticket: string; code: string };
    return Promise.resolve(
      body.ticket === 'ingreso-1' && body.code === GOOD_CODE
        ? respond(BENJI)
        : respond({ error: { code: 'auth_required', message: 'El código no es correcto.' } }, 401),
    );
  }
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

function renderApp(me: Me | null = BENJI) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // La sesión ya abierta: así la pantalla aparece sin esperar /auth/me.
  if (me) client.setQueryData(['auth', 'me'], me);
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
    fireEvent.click(within(dock).getByRole('button', { name: 'Iniciar barrido' }));
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
    // Las dos de puntaje 0 las descartó la IA (leyó solo el título): no salen,
    // pero un botón las muestra con su marca y se vuelven a ocultar (ADR-0117).
    expect(within(dossier).queryByText(/no tratar del tema/)).toBeNull();
    const discarded = articles.items.filter((a) =>
      a.concepts.every((c) => !c.is_relevant && c.relevance_score < 0.3),
    );
    expect(discarded).toHaveLength(2);
    fireEvent.click(within(dossier).getByRole('button', { name: 'Ver las 2 que descartó la IA' }));
    expect(within(list).getAllByRole('listitem')).toHaveLength(relevant.length + discarded.length);
    expect(within(list).getAllByText('Descartada por la IA')).toHaveLength(discarded.length);
    await waitFor(() => {
      expect(screen.getByTestId('globo').dataset.notas).toBe(
        String(relevant.length + discarded.length),
      );
    });
    fireEvent.click(
      within(dossier).getByRole('button', { name: 'Ocultar las 2 que descartó la IA' }),
    );
    expect(within(list).getAllByRole('listitem')).toHaveLength(relevant.length);

    // 6b. Fraccionado por plataforma, como Google (ADR-0117): «Facebook» deja
    //     solo esa en la lista y en el globo; la ficha abre la publicación.
    const platformTabs = within(dossier).getByRole('group', { name: 'Filtrar por plataforma' });
    expect(
      within(platformTabs)
        .getAllByRole('button')
        .map((b) => b.getAttribute('aria-label')),
    ).toEqual(['Todo: 4 notas', 'Noticias: 2 notas', 'Facebook: 1 nota', 'YouTube: 1 nota']);
    fireEvent.click(within(platformTabs).getByRole('button', { name: /^Facebook/ }));
    const onFacebook = (relevant as Article[]).filter((a) => a.platform === 'facebook');
    const [post] = onFacebook;
    if (!post) throw new Error('El fixture necesita una publicación relevante de Facebook.');
    expect(within(list).getAllByRole('listitem')).toHaveLength(onFacebook.length);
    await waitFor(() => {
      expect(screen.getByTestId('globo').dataset.notas).toBe(String(onFacebook.length));
    });
    fireEvent.click(
      within(list).getByRole('button', { name: new RegExp(post.title.slice(0, 20)) }),
    );
    const postCard = await within(screen.getByTestId('globo')).findByRole('article');
    expect(
      within(postCard)
        .getByRole('link', { name: /Ver publicación en Facebook/ })
        .getAttribute('href'),
    ).toBe(post.url);
    // Tocarla otra vez regresa a «Todo».
    fireEvent.click(within(platformTabs).getByRole('button', { name: /^Facebook/ }));
    expect(within(list).getAllByRole('listitem')).toHaveLength(relevant.length);
    await waitFor(() => {
      expect(screen.getByTestId('globo').dataset.notas).toBe(String(relevant.length));
    });
    // El conteo es facetado: con «Sin lugar» en «Filtro» bajan las pestañas, la
    // ventana dice los mismos números y coinciden con la lista (revisión del
    // 18/11/2026: la ventana contaba sobre todas).
    fireEvent.click(within(dossier).getByRole('button', { name: /^Filtro/ }));
    const filter = screen.getByRole('dialog', { name: 'Filtrar el expediente' });
    const location = within(filter).getByRole('region', { name: 'Ubicación' });
    fireEvent.click(within(location).getByRole('button', { name: 'Sin lugar' }));
    const unlocated = relevant.filter((a) => a.in_region === null);
    expect(
      within(platformTabs)
        .getAllByRole('button')
        .map((b) => b.getAttribute('aria-label')),
    ).toEqual(['Todo: 2 notas', 'Noticias: 1 nota', 'YouTube: 1 nota']);
    expect(within(list).getAllByRole('listitem')).toHaveLength(unlocated.length);
    const inFilter = within(filter).getByRole('group', { name: 'Plataformas a mostrar' });
    expect(
      within(inFilter)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Todas', 'Noticias1', 'YouTube1']);
    fireEvent.click(within(location).getByRole('button', { name: 'Todas' }));
    fireEvent.click(within(filter).getByRole('button', { name: 'Listo' }));
    expect(within(list).getAllByRole('listitem')).toHaveLength(relevant.length);

    // 7. El resumen se pliega aparte para dar todo el alto a la lista; el
    //    reporte sigue a la mano junto a las pestañas.
    expect(within(dossier).getByText('Estados')).toBeTruthy();
    fireEvent.click(within(dossier).getByRole('button', { name: 'Plegar el resumen' }));
    expect(within(dossier).queryByText('Estados')).toBeNull();
    expect(within(dossier).getByRole('button', { name: 'Ver reporte' })).toBeTruthy();
    expect(within(dossier).getByRole('button', { name: 'Descargar PDF' })).toBeTruthy();
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

    // 9. «Ver reporte» lo abre en una ventana, sin descargar nada (ADR-0111):
    //    la API lo arma en un iframe con sandbox. Esc la cierra.
    fireEvent.click(within(dossier).getByRole('button', { name: 'Ver reporte' }));
    const reportWindow = screen.getByRole('dialog', { name: 'Reporte' });
    const frame = within(reportWindow).getByTitle(/^Reporte: /);
    expect(frame.getAttribute('src')).toBe(`/api/v1/searches/${SEARCH_ID}/report/view`);
    expect(frame.getAttribute('sandbox')).not.toMatch(/allow-forms|allow-top-navigation/);
    expect(within(reportWindow).getByRole('button', { name: 'Descargar PDF' })).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Reporte' })).toBeNull();
    expect(reportRequests).toEqual([]);

    // 10. Reporte en PDF desde el expediente.
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });
    fireEvent.click(within(dossier).getByRole('button', { name: 'Descargar PDF' }));
    await waitFor(() => {
      expect(saved).toEqual(['reporte-extorsion-jalisco-2026-10-17.pdf']);
    });

    // 11. La flecha oculta el expediente y una pestaña en el borde lo regresa.
    fireEvent.click(within(dossier).getByRole('button', { name: 'Ocultar el expediente' }));
    expect(screen.queryByRole('complementary', { name: 'Expediente de la consulta' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Expediente ·/ }));
    expect(screen.getByRole('complementary', { name: 'Expediente de la consulta' })).toBeTruthy();
  }, 15000);

  it('el encabezado lleva de regreso al sistema principal de Oráculo', async () => {
    renderApp();
    const link = await screen.findByRole('link', { name: 'Regresar a Oráculo' });
    expect(link.getAttribute('href')).toBe('http://172.25.18.234/');
  });

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
    // Desde F12 (ADR-0107) el caso se divide en pestañas; las noticias tienen la suya.
    fireEvent.click(await screen.findByRole('tab', { name: 'Noticias (2)' }));
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
    // La cronología reemplaza a la lista; «Lista» la vuelve a mostrar.
    expect(await screen.findByRole('region', { name: 'Cronología' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Lista' }));
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
    // pestaña "Fuera de zona" las separa (§9 paso 7).
    const relevant = articles.items.filter((a) => a.concepts.some((c) => c.is_relevant));
    await waitFor(() => {
      expect(screen.getByTestId('globo').dataset.notas).toBe(String(relevant.length));
    });
    expect(within(list).getAllByRole('listitem')).toHaveLength(relevant.length);
    const outside = relevant.filter((a) => a.in_region === false).length;
    expect(
      within(list).getByRole('tab', { name: `Fuera de zona · ${String(outside)}` }),
    ).toBeTruthy();

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

    // 6. "No relevantes" suma las cercanas en la lista y en el globo a la vez;
    //    las que descartó la IA (menos de 0.3) salen solo con su botón (ADR-0117).
    const nearby = articles.items.filter((a) =>
      a.concepts.some((c) => c.is_relevant || c.relevance_score >= 0.3),
    );
    expect(nearby.length).toBeGreaterThan(relevant.length);
    expect(nearby.length).toBeLessThan(articles.items.length);
    const showIrrelevant = within(list).getByRole('checkbox', { name: 'No relevantes' });
    fireEvent.click(showIrrelevant);
    expect(within(list).getAllByRole('listitem')).toHaveLength(nearby.length);
    expect(screen.getByTestId('globo').dataset.notas).toBe(String(nearby.length));
    expect(within(list).getByText('Cercana')).toBeTruthy();
    expect(within(list).queryByText(/no tratar del tema/)).toBeNull();
    fireEvent.click(within(list).getByRole('button', { name: 'Ver las 2 que descartó la IA' }));
    expect(within(list).getAllByRole('listitem')).toHaveLength(articles.items.length);
    expect(within(list).getAllByText('Descartada por la IA')).toHaveLength(2);
    fireEvent.click(within(list).getByRole('button', { name: 'Ocultar las 2 que descartó la IA' }));
    fireEvent.click(showIrrelevant);
    expect(screen.getByTestId('globo').dataset.notas).toBe(String(relevant.length));

    // 6b. Las pestañas de plataforma cuentan con la pestaña de ubicación de la
    //     lista, igual que el expediente (revisión del 18/11/2026).
    const platformTabs = screen.getByRole('group', { name: 'Filtrar por plataforma' });
    expect(within(platformTabs).getByRole('button', { name: 'Todo: 4 notas' })).toBeTruthy();
    const unlocated = relevant.filter((a) => a.in_region === null);
    fireEvent.click(
      within(list).getByRole('tab', { name: `Sin ubicación · ${String(unlocated.length)}` }),
    );
    expect(
      within(platformTabs)
        .getAllByRole('button')
        .map((b) => b.getAttribute('aria-label')),
    ).toEqual(['Todo: 2 notas', 'Noticias: 1 nota', 'YouTube: 1 nota']);
    expect(within(list).getAllByRole('listitem')).toHaveLength(unlocated.length);
    fireEvent.click(within(list).getByRole('tab', { name: /^Todas/ }));

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

describe('acceso con usuario, contraseña y código (ADR-0043)', () => {
  it('sin sesión pide usuario y contraseña, luego el código, y abre el monitor', async () => {
    renderApp(null);

    const user = await screen.findByLabelText('Usuario');
    const password = screen.getByLabelText('Contraseña');
    expect(screen.queryByRole('navigation', { name: 'Secciones' })).toBeNull();
    expect(password.getAttribute('type')).toBe('password');
    expect(password.getAttribute('autocomplete')).toBe('current-password');
    const next = screen.getByRole('button', { name: 'Continuar' });
    expect((next as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(user, { target: { value: 'benji' } });
    fireEvent.change(password, { target: { value: 'equivocada-1' } });
    fireEvent.click(next);
    expect((await screen.findByRole('alert')).textContent).toContain('incorrectos');

    fireEvent.change(password, { target: { value: GOOD_PASSWORD } });
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
    const code = await screen.findByLabelText('Código de 6 dígitos');
    expect(code.getAttribute('inputmode')).toBe('numeric');
    fireEvent.change(code, { target: { value: '000000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));
    expect((await screen.findByRole('alert')).textContent).toContain('código');

    fireEvent.change(code, { target: { value: GOOD_CODE } });
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));
    expect(await screen.findByRole('button', { name: 'Salir' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Mi contraseña' })).toBeTruthy();
    expect(screen.getByText('Benjamin')).toBeTruthy();
    const nav = screen.getByRole('navigation', { name: 'Secciones' });
    expect(within(nav).getByRole('link', { name: 'Accesos' })).toBeTruthy();
  });

  it('por Oráculo y sin llave válida, avisa en lugar de pedir usuario y contraseña', async () => {
    ROUTES['app-config'] = { oraculo_url: 'http://172.25.18.234', via_gateway: true };
    try {
      renderApp(null);

      expect(await screen.findByRole('heading', { name: 'Acceso denegado' })).toBeTruthy();
      expect(screen.getByRole('alert').textContent).toContain('iniciar sesión en Oráculo');
      expect(screen.queryByLabelText('Usuario')).toBeNull();
      expect(screen.queryByLabelText('Contraseña')).toBeNull();
    } finally {
      ROUTES['app-config'] = { oraculo_url: 'http://172.25.18.234' };
    }
  });

  it('sin entrada con contraseña, ni el acceso directo pide usuario (ADR-0121)', async () => {
    ROUTES['app-config'] = { oraculo_url: 'http://172.25.18.234', password_login: false };
    try {
      renderApp(null);

      expect(await screen.findByRole('heading', { name: 'Acceso denegado' })).toBeTruthy();
      expect(screen.queryByLabelText('Usuario')).toBeNull();
      expect(screen.queryByLabelText('Contraseña')).toBeNull();
    } finally {
      ROUTES['app-config'] = { oraculo_url: 'http://172.25.18.234' };
    }
  });

  it('sin entrada con contraseña y con sesión, no hay «Salir» ni «Mi contraseña»', async () => {
    ROUTES['app-config'] = { oraculo_url: 'http://172.25.18.234', password_login: false };
    try {
      renderApp();

      expect(await screen.findByText('Benjamin')).toBeTruthy();
      expect(screen.queryByRole('button', { name: 'Salir' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Mi contraseña' })).toBeNull();
    } finally {
      ROUTES['app-config'] = { oraculo_url: 'http://172.25.18.234' };
    }
  });

  it('por Oráculo con sesión, no ofrece «Salir» ni «Mi contraseña» del monitor', async () => {
    ROUTES['app-config'] = { oraculo_url: 'http://172.25.18.234', via_gateway: true };
    try {
      renderApp();

      expect(await screen.findByRole('link', { name: 'Regresar a Oráculo' })).toBeTruthy();
      expect(screen.getByText('Benjamin')).toBeTruthy();
      expect(screen.queryByRole('button', { name: 'Salir' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Mi contraseña' })).toBeNull();
    } finally {
      ROUTES['app-config'] = { oraculo_url: 'http://172.25.18.234' };
    }
  });

  it('un usuario normal no ve «Estado del sistema» ni «Accesos», ni entrando por la URL', () => {
    window.location.hash = '#/accesos';
    renderApp({
      ...BENJI,
      username: 'ana',
      display_name: 'Ana',
      role: 'user',
      sections: ['explorar', 'casos', 'conceptos', 'historial'],
    });

    const nav = screen.getByRole('navigation', { name: 'Secciones' });
    const tabs = within(nav)
      .getAllByRole('link')
      .map((t) => t.getAttribute('href'));
    expect(tabs).toContain('#/historial');
    expect(tabs).not.toContain('#/estado');
    expect(tabs).not.toContain('#/accesos');
    expect(tabs).not.toContain('#/envios');
    expect(within(nav).getByRole('link', { current: 'page' }).getAttribute('href')).toBe(
      '#/explorar',
    );
  });
});
