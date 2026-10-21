/**
 * Pantalla Explorar (§14.1, pantalla principal; estilo de las imágenes de
 * referencia de Benji): el globo domina, sobre el universo, con paneles
 * translúcidos a los lados.
 *
 * - Izquierda: búsqueda (al terminar, un renglón con sus descargas) y lista de
 *   noticias. La lista ocupa el espacio libre y el panel se puede ocultar
 *   ("Ocultar ‹") para ver el globo completo; en pantallas angostas se oculta
 *   solo al elegir una noticia, para que se vea su ficha.
 * - Derecha: libre, para que el globo se vea completo (Benji quitó las
 *   gráficas "Top 5 estados" y "Tipos de noticias": no aportaban).
 * - Abajo: giro, día/noche, velocidad y leyenda de precisión.
 * - Abajo al centro: el aviso "Búsqueda lista" cuando termina la que se vio correr.
 *
 * Lee el store y pide los datos con los hooks; el globo y los paneles se
 * sincronizan a través del store.
 */
import { useEffect, useMemo } from 'react';

import { useConcepts } from '../../hooks/useConcepts';
import { useSearch, useSearchArticles } from '../../hooks/useSearches';
import { type Article, isFinished } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { SpaceBackground } from '../Space/SpaceBackground';
import { FinishToast, GlobeControls, PrecisionLegend } from './Controls';
import { ExploreGlobe } from './ExploreGlobe';
import { visibleArticles } from './format';
import { ResultsList } from './ResultsList';
import { SearchPanel } from './SearchPanel';
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
  // Lo mismo para el globo y la lista: nunca muestran notas distintas.
  const shown = useMemo(
    () => visibleArticles(articles, showIrrelevant),
    [articles, showIrrelevant],
  );
  const hasResults = finished && articles.length > 0;
  const panelOpen = useExplorerStore((s) => s.panelOpen);
  const setPanelOpen = useExplorerStore((s) => s.setPanelOpen);
  const articleId = useExplorerStore((s) => s.articleId);
  const finishedNotice = useFinishNotice(search);

  useEffect(() => {
    if (articleId !== null && isNarrowScreen()) setPanelOpen(false);
  }, [articleId, setPanelOpen]);

  return (
    <div className="relative h-full overflow-hidden bg-[#02030a]">
      <SpaceBackground />
      <ExploreGlobe articles={shown} colors={colors} />

      <aside
        aria-label="Búsqueda y noticias"
        className={`pointer-events-none absolute inset-y-0 left-0 flex w-full flex-col gap-3 overflow-y-auto p-4 transition-[transform,visibility] duration-300 sm:w-[24rem] ${
          panelOpen ? 'visible translate-x-0' : 'invisible -translate-x-full'
        }`}
      >
        <div className="pointer-events-auto shrink-0">
          {/* Otra búsqueda vuelve a mostrar el panel completo (o compacto). */}
          <SearchPanel key={searchId ?? 'nueva'} />
        </div>
        {hasResults && (
          <div className="pointer-events-auto flex min-h-[14rem] flex-1 flex-col">
            <ResultsList articles={shown} total={articles.length} colors={colors} />
          </div>
        )}
      </aside>

      {!panelOpen && (
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
        <div className="pointer-events-auto">
          <GlobeControls />
        </div>
      </div>

      <FinishToast notice={finishedNotice.notice} onClose={finishedNotice.dismiss} />
    </div>
  );
}
