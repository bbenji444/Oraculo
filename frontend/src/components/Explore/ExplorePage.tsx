/**
 * Pantalla Explorar (§14.1, pantalla principal; estilo de las imágenes de
 * referencia de Benji): el globo domina, sobre el universo, con paneles
 * translúcidos a los lados.
 *
 * - Izquierda: la última corrida del monitor FGR (si no hay búsqueda abierta),
 *   la búsqueda (al terminar, compacta con sus descargas) y la cronología o la
 *   lista de noticias, que ocupa el espacio libre. La búsqueda y la cronología
 *   se pliegan cada una por su lado («Ocultar ‹» y «›»). En pantallas
 *   angostas el panel entero se oculta solo al elegir una noticia, para que se
 *   vea su ficha.
 * - Derecha: libre, para que el globo se vea completo (Benji quitó las
 *   gráficas "Top 5 estados" y "Tipos de noticias": no aportaban).
 * - Izquierda, debajo de la búsqueda: la cronología (F12.7), una línea vertical
 *   con cada hecho, del más reciente al más viejo, sin repetidos; sus filtros
 *   se aplican al globo. «☰ Lista» la cambia por la lista de noticias.
 * - Abajo a la derecha: giro, día/noche, velocidad y leyenda de precisión.
 * - Abajo al centro: el aviso "Búsqueda lista" cuando termina la que se vio correr.
 * - Modo caso (9.6): con `#/explorar?caso=<id>` el globo muestra el muro del
 *   caso (`CaseWall`) en lugar de las noticias de la búsqueda.
 * - «Mis casos» (9.6): mis casos como marcadores ámbar (`CasesOnGlobe`).
 * - «✕ Limpiar globo» (9.6): quita resultados, nota elegida y muro, y vuelve a
 *   México con el formulario listo para otra búsqueda.
 *
 * Lee el store y pide los datos con los hooks; el globo y los paneles se
 * sincronizan a través del store.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useMemo, useState } from 'react';

import { useConcepts } from '../../hooks/useConcepts';
import { useSearch, useSearchArticles } from '../../hooks/useSearches';
import { type Article, isFinished } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import { wallCaseFromHash } from '../../map/muro/orbit';
import { SpaceBackground } from '../Space/SpaceBackground';
import { CasesOnGlobe } from './CasesOnGlobe';
import { CaseWall } from './CaseWall';
import { FinishToast, GlobeControls, PrecisionLegend } from './Controls';
import { ExploreGlobe } from './ExploreGlobe';
import { GlobeUnavailable, GraphicsBoundary } from './GraphicsBoundary';
import { LatestRunCard } from './LatestRunCard';
import { visibleArticles } from './format';
import { ResultsList } from './ResultsList';
import { SearchPanel } from './SearchPanel';
import { Chronology } from './Chronology';
import { applyTimeline } from './timelineData';
import { GLASS } from './ui';
import { useFinishNotice } from './useFinishNotice';

// Lista vacía estable: un arreglo nuevo en cada render haría redibujar el globo.
const NO_ARTICLES: Article[] = [];
// Por debajo de este ancho el panel tapa el globo (Tailwind `md`): al elegir una
// noticia se oculta para que se vea su ficha.
const NARROW_SCREEN = '(max-width: 767px)';

function isNarrowScreen(): boolean {
  // Sin matchMedia (pruebas, navegadores viejos) se trata como pantalla ancha.
  return typeof window.matchMedia === 'function' && window.matchMedia(NARROW_SCREEN).matches;
}

export function ExplorePage() {
  const searchId = useExplorerStore((s) => s.searchId);
  const search = useSearch(searchId).data;
  const finished = search !== undefined && isFinished(search.status);
  const articles = useSearchArticles(searchId, finished).data ?? NO_ARTICLES;
  const concepts = useConcepts().data;
  const colors = useMemo(
    () => new Map((concepts ?? []).map((c) => [c.id, c.color] as const)),
    [concepts],
  );
  const showIrrelevant = useExplorerStore((s) => s.showIrrelevant);
  const relevant = useMemo(
    () => visibleArticles(articles, showIrrelevant),
    [articles, showIrrelevant],
  );
  const range = useTimelineStore((s) => s.range);
  const categoryId = useTimelineStore((s) => s.categoryId);
  const stateCode = useTimelineStore((s) => s.stateCode);
  const clearTimeline = useTimelineStore((s) => s.clear);
  // Lo mismo para el globo, la lista y la línea del tiempo: nunca muestran notas distintas.
  const shown = useMemo(
    () => applyTimeline(relevant, { range, categoryId, stateCode }),
    [relevant, range, categoryId, stateCode],
  );
  const hasResults = finished && articles.length > 0;
  const panelOpen = useExplorerStore((s) => s.panelOpen);
  const setPanelOpen = useExplorerStore((s) => s.setPanelOpen);
  const articleId = useExplorerStore((s) => s.articleId);
  const finishedNotice = useFinishNotice(search);
  const earth = useExplorerStore((s) => s.earth);
  const listOpen = useTimelineStore((s) => s.listOpen);
  const wallCaseId = useExplorerStore((s) => s.wallCaseId);
  const inWall = wallCaseId !== null;
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const showCases = useExplorerStore((s) => s.showCases);
  const somethingOnGlobe = searchId !== null || articleId !== null;

  // La URL manda: `#/explorar?caso=<id>` abre el muro (se puede compartir y recargar).
  useEffect(() => {
    const sync = () => {
      const caseId = wallCaseFromHash(window.location.hash);
      const store = useExplorerStore.getState();
      if (caseId !== null && caseId !== store.wallCaseId) store.openWall(caseId);
      if (caseId === null && store.wallCaseId !== null) store.closeWall();
    };
    sync();
    window.addEventListener('hashchange', sync);
    return () => {
      window.removeEventListener('hashchange', sync);
    };
  }, []);

  useEffect(() => {
    if (articleId !== null && isNarrowScreen()) setPanelOpen(false);
  }, [articleId, setPanelOpen]);

  // Otra búsqueda empieza sin filtros de la línea del tiempo.
  useEffect(() => {
    clearTimeline();
  }, [searchId, clearTimeline]);

  return (
    // data-earth: los paneles de vidrio se oscurecen en modo día (ver GLASS).
    // overflow-clip y no hidden: con hidden, scrollIntoView de una lista podía
    // desplazar la pantalla entera y dejar una franja negra abajo.
    <div data-earth={earth} className="relative h-full overflow-clip bg-[#02030a]">
      {/* Cada uno con su red: si la tarjeta de video falla, el resto sigue
          funcionando en lugar de quedar la pantalla en blanco. */}
      <GraphicsBoundary fallback={null}>
        <SpaceBackground />
      </GraphicsBoundary>
      <GraphicsBoundary fallback={<GlobeUnavailable />}>
        <ExploreGlobe articles={inWall ? NO_ARTICLES : shown} colors={colors} onMap={setMap} />
      </GraphicsBoundary>
      <CaseWall map={map} />
      <CasesOnGlobe map={map} />

      <aside
        aria-label="Búsqueda y noticias"
        className={`pointer-events-none absolute inset-y-0 left-0 flex w-full flex-col gap-3 overflow-y-auto p-4 transition-[transform,visibility] duration-300 sm:w-[24rem] ${
          panelOpen && !inWall ? 'visible translate-x-0' : 'invisible -translate-x-full'
        }`}
      >
        {searchId === null && (
          // Acceso directo a la última corrida del monitor FGR (F12.8).
          <div className="pointer-events-auto shrink-0">
            <LatestRunCard />
          </div>
        )}
        <div className="pointer-events-auto shrink-0">
          {/* Otra búsqueda vuelve a mostrar el panel completo (o compacto). */}
          <SearchPanel key={searchId ?? 'nueva'} />
        </div>
        {/* Debajo de la búsqueda, la cronología; «☰ Lista» la cambia por la lista. */}
        {hasResults && (
          <div className="pointer-events-auto flex min-h-[14rem] flex-1 flex-col">
            {listOpen ? (
              <ResultsList articles={shown} total={articles.length} colors={colors} />
            ) : (
              <Chronology articles={relevant} />
            )}
          </div>
        )}
      </aside>

      {!panelOpen && !inWall && (
        <button
          type="button"
          onClick={() => {
            setPanelOpen(true);
          }}
          className={`${GLASS} absolute left-4 top-4 flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-100 hover:bg-slate-900/80 focus-visible:outline-2 focus-visible:outline-sky-400`}
        >
          › Búsqueda y noticias{hasResults ? ` (${String(shown.length)})` : ''}
        </button>
      )}

      <div className="pointer-events-none absolute bottom-8 right-4 hidden flex-col items-end gap-2 sm:flex">
        <div className="pointer-events-auto">
          <PrecisionLegend />
        </div>
        <div className="pointer-events-auto flex gap-2">
          <button
            type="button"
            aria-pressed={showCases}
            onClick={() => {
              useExplorerStore.getState().setShowCases(!showCases);
            }}
            title="Ver mis casos abiertos sobre el globo; clic en uno abre su muro"
            className={`${GLASS} px-3 py-2 text-xs font-medium focus-visible:outline-2 focus-visible:outline-sky-400 ${
              showCases ? 'text-amber-200' : 'text-slate-200 hover:bg-slate-900/80'
            }`}
          >
            {showCases ? '● Mis casos' : '○ Mis casos'}
          </button>
          <GlobeControls />
        </div>
      </div>

      {somethingOnGlobe && !inWall && (
        <button
          type="button"
          onClick={() => {
            useExplorerStore.getState().clearGlobe();
          }}
          title="Quita los resultados del globo y deja listo para otra búsqueda (esta queda en Historial)"
          className={`${GLASS} absolute left-1/2 top-3 z-10 -translate-x-1/2 px-3 py-1.5 text-xs font-medium text-slate-100 hover:bg-slate-900/80 focus-visible:outline-2 focus-visible:outline-sky-400`}
        >
          ✕ Limpiar globo
        </button>
      )}

      <FinishToast notice={finishedNotice.notice} onClose={finishedNotice.dismiss} />
    </div>
  );
}
