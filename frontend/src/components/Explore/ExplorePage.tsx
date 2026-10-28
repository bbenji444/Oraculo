/**
 * Pantalla Explorar (§14.1, pantalla principal; estilo de las imágenes de
 * referencia de Benji): el globo domina, sobre el universo, con paneles
 * translúcidos a los lados.
 *
 * Tiene dos acomodos de los paneles, que comparten el globo y los datos:
 * - «Centro de mando» (el principal, ADR-0037): consola de consulta abajo y
 *   expediente a la derecha (components/Mando);
 * - de columna (`?clasico` en la URL, ADR-0036): lo que se describe abajo.
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
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { useSearch, useSearchArticles } from '../../hooks/useSearches';
import { type Article, isFinished } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useMandoStore } from '../../store/mando';
import { useTimelineStore } from '../../store/timeline';
import { NARROW_MAX_WIDTH } from '../../map/framing';
import { wallCaseFromHash } from '../../map/muro/orbit';
import { DOSSIER_RESERVE_PX, MandoPanels } from '../Mando/MandoPanels';
import { isMandoMode } from '../Mando/mission';
import { ScanOverlay } from '../Mando/ScanOverlay';
import { CasesOnGlobe } from './CasesOnGlobe';
import { CaseWall } from './CaseWall';
import { FinishToast, GlobeControls, MyCasesToggle, PrecisionLegend } from './Controls';
import { ExploreGlobe } from './ExploreGlobe';
import { GlobeUnavailable, GraphicsBoundary } from './GraphicsBoundary';
import { LatestRunCard } from './LatestRunCard';
import { visibleArticles } from './format';
import { ResultsList } from './ResultsList';
import { SearchPanel } from './SearchPanel';
import { Chronology } from './Chronology';
import { applyTimeline } from './timelineData';
import { useFinishNotice } from './useFinishNotice';

// Lista vacía estable: un arreglo nuevo en cada render haría redibujar el globo.
const NO_ARTICLES: Article[] = [];
// Ancho de la columna de la izquierda (sm:w-[24rem]): lo que se corre el globo.
const COLUMN_WIDTH_PX = 384;
// Por debajo de este ancho el panel tapa el globo (Tailwind `md`): al elegir una
// noticia se oculta para que se vea su ficha.
const NARROW_SCREEN = '(max-width: 767px)';

function isNarrowScreen(): boolean {
  // Sin matchMedia (pruebas, navegadores viejos) se trata como pantalla ancha.
  return typeof window.matchMedia === 'function' && window.matchMedia(NARROW_SCREEN).matches;
}

interface ExplorePageProps {
  /**
   * Si Explorar está a la vista. App la deja montada al cambiar de pestaña
   * para no destruir y volver a crear el globo cada vez (26/10/2026).
   */
  active?: boolean;
}

export function ExplorePage({ active = true }: ExplorePageProps) {
  // Diseño «Centro de mando» (el principal desde el 27/10/2026); con `?clasico`
  // en la URL, el de columna. Se lee al montar: cambiarlo es abrir otra dirección.
  const [mando] = useState(isMandoMode);
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
  const categoryIds = useTimelineStore((s) => s.categoryIds);
  const stateCode = useTimelineStore((s) => s.stateCode);
  const clearTimeline = useTimelineStore((s) => s.clear);
  // Lo mismo para el globo, la lista y la línea del tiempo: nunca muestran notas distintas.
  const shown = useMemo(
    () => applyTimeline(relevant, { range, categoryIds, stateCode }),
    [relevant, range, categoryIds, stateCode],
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
  const somethingOnGlobe = searchId !== null || articleId !== null;
  // Encuadre del globo (Benji, 27/10/2026): con la columna de la izquierda a la
  // vista, el mundo se corre a la derecha; con la búsqueda y la cronología
  // plegadas (o el panel oculto), se centra y crece. En celular la columna
  // tapa todo y el globo se queda centrado.
  const wide = useMediaQuery(`(min-width: ${String(NARROW_MAX_WIDTH + 1)}px)`, true);
  const searchCollapsed = useExplorerStore((s) => s.searchCollapsed);
  const timelineOpen = useTimelineStore((s) => s.open);
  const columnShown =
    wide &&
    panelOpen &&
    !inWall &&
    (!searchCollapsed || (hasResults && (timelineOpen || listOpen)));
  // En el Centro de mando el globo flota encima de la consola de abajo y se
  // corre a la izquierda cuando el expediente está abierto a la derecha.
  const dossierOpen = useMandoStore((s) => s.dossierOpen);
  const dockHeight = useMandoStore((s) => s.dockHeight);
  const insets = mando
    ? {
        left: 0,
        right: wide && hasResults && dossierOpen && !inWall ? DOSSIER_RESERVE_PX : 0,
        bottom: wide && !inWall ? dockHeight : 0,
      }
    : { left: columnShown ? COLUMN_WIDTH_PX : 0, right: 0, bottom: 0 };

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
    // data-earth: los paneles de vidrio se oscurecen en modo día (ver GLASS en ui.ts).
    // overflow-clip y no hidden: con hidden, scrollIntoView de una lista podía
    // desplazar la pantalla entera y dejar una franja negra abajo.
    // Sin fondo propio: detrás va el universo que dibuja App.
    // data-dossier: en el Centro de mando, los controles del mapa se recorren
    // a la izquierda del expediente (styles/mando.css).
    <div
      data-earth={earth}
      data-dossier={mando && insets.right > 0 ? 'open' : undefined}
      className="relative h-full overflow-clip"
    >
      {/* El universo de atrás lo dibuja App para todas las pestañas. El globo
          tiene su red: si la tarjeta de video falla, el resto sigue
          funcionando en lugar de quedar la pantalla en blanco. */}
      <GraphicsBoundary fallback={<GlobeUnavailable />}>
        <ExploreGlobe
          articles={inWall ? NO_ARTICLES : shown}
          colors={colors}
          onMap={setMap}
          active={active}
          insetLeft={insets.left}
          insetRight={insets.right}
          insetBottom={insets.bottom}
          clearHeader={mando}
        />
      </GraphicsBoundary>
      {mando && !inWall && (
        <ScanOverlay
          search={search}
          notice={finishedNotice.notice}
          right={insets.right}
          bottom={insets.bottom}
        />
      )}
      {/* Los paneles van debajo del encabezado; el universo y el globo, detrás
          de todo (también del encabezado, que no tiene fondo). */}
      <div className="capa-paneles absolute inset-x-0 bottom-0 top-[var(--header-h)]">
        <CaseWall map={map} />
        <CasesOnGlobe map={map} />

        {mando && !inWall && (
          <MandoPanels
            active={active}
            search={search}
            hasResults={hasResults}
            articles={articles}
            relevant={relevant}
            shown={shown}
            colors={colors}
            rightReserve={insets.right}
          />
        )}
        {!mando && (
          <>
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
                className="hud-btn hud-btn--sm absolute left-4 top-4 bg-[#050d12]/90"
              >
                › Búsqueda y noticias{hasResults ? ` (${String(shown.length)})` : ''}
              </button>
            )}

            <div className="pointer-events-none absolute bottom-8 right-4 hidden flex-col items-end gap-2 sm:flex">
              <div className="pointer-events-auto">
                <PrecisionLegend />
              </div>
              <div className="pointer-events-auto flex gap-2">
                <MyCasesToggle />
                <GlobeControls />
              </div>
            </div>
          </>
        )}

        {/* En el Centro de mando lo hace «Nueva consulta», en la consola. */}
        {somethingOnGlobe && !inWall && !mando && (
          <button
            type="button"
            onClick={() => {
              useExplorerStore.getState().clearGlobe();
            }}
            title="Quita los resultados del globo y deja listo para otra búsqueda (esta queda en Historial)"
            className="hud-btn hud-btn--sm absolute left-1/2 top-3 z-10 -translate-x-1/2 bg-[#050d12]/90"
          >
            ✕ Limpiar globo
          </button>
        )}

        {/* En el Centro de mando el aviso es el letrero grande sobre el globo. */}
        {!mando && <FinishToast notice={finishedNotice.notice} onClose={finishedNotice.dismiss} />}
      </div>
    </div>
  );
}
