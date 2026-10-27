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
      className={`${GLASS} hud-panel--interactive group flex w-full items-center gap-3 border-sky-400/35 px-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-sky-400`}
    >
      <span aria-hidden="true" className="hud-radar size-9" />
      <span className="flex min-w-0 flex-col gap-1">
        <span className="font-display text-[10px] tracking-[0.2em] text-sky-300 uppercase">
          {automaticRunLabel(run)}
        </span>
        <span className="text-[13px] font-medium text-slate-50">
          {run.concepts.map((c) => c.name).join(', ')} · {run.region_name}
        </span>
        <span className="text-[11px] text-slate-400">
          {run.results_count} notas · {run.credits_used} créditos ·{' '}
          <span className="text-sky-300 transition-colors group-hover:text-sky-100">
            Abrir en el globo ›
          </span>
        </span>
      </span>
    </button>
  );
}
