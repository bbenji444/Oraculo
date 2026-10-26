/**
 * Acceso directo a la última corrida del monitor automático FGR (F12.8,
 * ADR-0031): arriba del panel de búsqueda, cuando no hay ninguna abierta.
 *
 * El monitor corre solo a las 07:00, 15:00 y 23:00; con esta tarjeta el
 * analista abre la más reciente en el globo con un clic, sin ir al historial.
 *
 * No hace: no lanza corridas (eso es el reloj del servidor) ni pide datos por
 * su cuenta: usa el mismo historial que la pestaña Historial.
 */
import { useSearchHistory } from '../../hooks/useSearches';
import { useExplorerStore } from '../../store/explorer';
import { automaticRunLabel, latestRun } from './format';
import { GLASS } from './ui';

export function LatestRunCard() {
  const history = useSearchHistory();
  const run = latestRun(history.data?.pages.flatMap((page) => page.items) ?? []);
  const restoreSearch = useExplorerStore((s) => s.restoreSearch);
  if (!run) {
    return null;
  }
  return (
    <button
      type="button"
      onClick={() => {
        restoreSearch({
          searchId: run.search_id,
          regionId: run.region_id,
          conceptIds: run.concepts.map((c) => c.id),
          dateFrom: run.date_from,
          dateTo: run.date_to,
          providers: run.providers,
        });
      }}
      className={`${GLASS} group flex w-full flex-col gap-1 border-sky-400/30 px-4 py-3 text-left transition-colors hover:border-sky-300/60 hover:bg-sky-400/[0.06] focus-visible:outline-2 focus-visible:outline-sky-400`}
    >
      <span className="titulo-oraculo text-[10px] font-bold text-sky-300">
        <span aria-hidden="true">◉ </span>
        {automaticRunLabel(run)}
      </span>
      <span className="text-[13px] font-medium text-slate-100">
        {run.concepts.map((c) => c.name).join(', ')} · {run.region_name}
      </span>
      <span className="text-[11px] text-slate-400">
        {run.results_count} notas · {run.credits_used} créditos ·{' '}
        <span className="text-sky-300 group-hover:text-sky-200">Abrir en el globo ›</span>
      </span>
    </button>
  );
}
