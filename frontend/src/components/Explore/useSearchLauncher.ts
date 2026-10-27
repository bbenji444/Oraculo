/**
 * Todo lo necesario para lanzar una búsqueda desde el formulario: lo que se
 * mandaría, su costo estimado y si se puede lanzar ya.
 *
 * Lo usan el panel de búsqueda (diseño «consola táctica») y la consola de
 * misión (diseño «Centro de mando»): los dos lanzan igual y con las mismas
 * reglas, solo se ven distinto.
 *
 * No hace: no dibuja nada ni decide textos; eso es de cada diseño.
 */
import { useEstimate, useSearch, useStartSearch } from '../../hooks/useSearches';
import { useSources } from '../../hooks/useSources';
import { isFinished } from '../../services/searches';
import { chosenSources } from '../../services/sources';
import { searchInput, useExplorerStore } from '../../store/explorer';

/**
 * @returns
 * - `input`: cuerpo de la búsqueda, o `null` si falta región, concepto o fuente;
 * - `estimate`, `start`, `sources`: las consultas de TanStack Query;
 * - `providers`: fuentes encendidas (o `undefined` mientras cargan);
 * - `noSources`: si se apagaron todas;
 * - `busy`: si ya hay una búsqueda en curso;
 * - `blocked`: si el botón debe apagarse (falta algo, se pasa del tope o no
 *   hay llave de la IA).
 */
export function useSearchLauncher() {
  const regionId = useExplorerStore((s) => s.regionId);
  const conceptIds = useExplorerStore((s) => s.conceptIds);
  const range = useExplorerStore((s) => s.range);
  const searchId = useExplorerStore((s) => s.searchId);
  const openSearch = useExplorerStore((s) => s.openSearch);
  const storedSources = useExplorerStore((s) => s.sources);
  const setSources = useExplorerStore((s) => s.setSources);
  const sources = useSources();
  // Sin la lista de fuentes (cargando o con error), se manda sin `providers`
  // y el servidor usa las de por defecto (F12.2).
  const providers = sources.data ? chosenSources(sources.data, storedSources) : undefined;
  const noSources = providers?.length === 0;
  const input = searchInput({ regionId, conceptIds, range }, providers);
  const estimate = useEstimate(input);
  const start = useStartSearch(openSearch);
  const running = useSearch(searchId).data;
  const busy = start.isPending || (running !== undefined && !isFinished(running.status));
  const blocked =
    !input || !estimate.data || estimate.data.over_limit || !estimate.data.llm.configured;
  return {
    input,
    estimate,
    start,
    sources,
    setSources,
    providers,
    noSources,
    running,
    busy,
    blocked,
  };
}
