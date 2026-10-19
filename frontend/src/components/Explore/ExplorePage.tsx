/**
 * Pantalla Explorar (§14.1, pantalla principal; estilo de las imágenes de
 * referencia de Benji): el globo domina, sobre el universo, con paneles
 * translúcidos a los lados.
 *
 * - Izquierda: búsqueda, lista de noticias y Descargas.
 * - Derecha: libre, para que el globo se vea completo (Benji quitó las
 *   gráficas "Top 5 estados" y "Tipos de noticias": no aportaban).
 * - Abajo: giro, día/noche, velocidad y leyenda de precisión.
 *
 * Lee el store y pide los datos con los hooks; el globo y los paneles se
 * sincronizan a través del store.
 */
import { useMemo } from 'react';

import { useConcepts } from '../../hooks/useConcepts';
import { useSearch, useSearchArticles } from '../../hooks/useSearches';
import { type Article, isFinished } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { SpaceBackground } from '../Space/SpaceBackground';
import { GlobeControls, DownloadsPanel, PrecisionLegend } from './Controls';
import { ExploreGlobe } from './ExploreGlobe';
import { visibleArticles } from './format';
import { ResultsList } from './ResultsList';
import { SearchPanel } from './SearchPanel';

// Lista vacía estable: un arreglo nuevo en cada render haría redibujar el globo.
const NO_ARTICLES: Article[] = [];

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

  return (
    <div className="relative h-full overflow-hidden bg-[#02030a]">
      <SpaceBackground />
      <ExploreGlobe articles={shown} colors={colors} />

      <aside className="pointer-events-none absolute inset-y-0 left-0 flex w-full flex-col gap-3 overflow-y-auto p-4 sm:w-[24rem]">
        <div className="pointer-events-auto">
          <SearchPanel />
        </div>
        {hasResults && (
          <div className="pointer-events-auto flex max-h-[28rem] min-h-[14rem] flex-col">
            <ResultsList articles={shown} colors={colors} />
          </div>
        )}
        <div className="pointer-events-auto">
          <DownloadsPanel />
        </div>
      </aside>

      <div className="pointer-events-none absolute bottom-8 right-4 hidden flex-col items-end gap-2 sm:flex">
        <div className="pointer-events-auto">
          <PrecisionLegend />
        </div>
        <div className="pointer-events-auto">
          <GlobeControls />
        </div>
      </div>
    </div>
  );
}
