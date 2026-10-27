/**
 * Pantalla Historial (§14.1): las búsquedas anteriores de la persona, de la más
 * reciente a la más vieja, con su estado, notas y costo. "Abrir en el globo"
 * la vuelve a mostrar en Explorar sin gastar nada (las notas ya están
 * guardadas).
 */
import { useSearchHistory } from '../../hooks/useSearches';
import type { Search } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import {
  automaticRunLabel,
  formatMexicoCity,
  formatRange,
  formatUsd,
  providersLabel,
} from '../Explore/format';

const STATUS_LABEL: Record<Search['status'], { text: string; className: string }> = {
  pending: { text: 'En cola', className: 'bg-slate-700 text-slate-200' },
  running: { text: 'Corriendo', className: 'bg-sky-500/20 text-sky-200' },
  completed: { text: 'Terminada', className: 'bg-emerald-500/20 text-emerald-200' },
  partial: { text: 'Parcial', className: 'bg-amber-500/20 text-amber-200' },
  failed: { text: 'Falló', className: 'bg-rose-500/20 text-rose-200' },
};

function reopen(search: Search) {
  useExplorerStore.getState().restoreSearch({
    searchId: search.search_id,
    regionId: search.region_id,
    conceptIds: search.concepts.map((c) => c.id),
    dateFrom: search.date_from,
    dateTo: search.date_to,
    providers: search.providers,
  });
  window.location.hash = '#/explorar';
}

export function HistoryPage() {
  const history = useSearchHistory();
  const searches = history.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="h-full overflow-y-auto px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <h2 className="titulo-oraculo text-base font-bold text-sky-50">Historial de búsquedas</h2>
        <p className="mt-1 text-sm text-slate-400">
          Reabrir una búsqueda no gasta créditos: sus notas ya están guardadas.
        </p>
        {history.isPending && <p className="mt-6 text-sm text-slate-400">Cargando…</p>}
        {history.error && <p className="mt-6 text-sm text-rose-300">{history.error.message}</p>}
        {history.isSuccess && searches.length === 0 && (
          <p className="mt-6 text-sm text-slate-400">Todavía no hay búsquedas.</p>
        )}
        <ul className="mt-6 space-y-3">
          {searches.map((search) => {
            const status = STATUS_LABEL[search.status];
            const automatic = automaticRunLabel(search);
            return (
              <li
                key={search.search_id}
                className={`flex flex-wrap items-center gap-4 rounded-2xl border px-4 py-3 ${
                  automatic
                    ? 'border-sky-400/30 bg-sky-400/[0.04] shadow-[0_0_18px_rgb(0_210_255/0.06)]'
                    : 'border-slate-800 bg-slate-900/70'
                }`}
              >
                <div className="min-w-0 flex-1">
                  {automatic && (
                    // Corrida del reloj (F12.8): la ven todos los analistas.
                    <p className="titulo-oraculo mb-1 text-[10px] font-bold text-sky-300">
                      <span aria-hidden="true">◉ </span>
                      {automatic}
                    </p>
                  )}
                  <p className="font-medium text-slate-100">
                    {search.concepts.map((c) => c.name).join(', ')} · {search.region_name}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {formatRange(search.date_from, search.date_to)} · pedida el{' '}
                    {formatMexicoCity(search.created_at)}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {/* Antes de F12.2 las búsquedas no guardaban con qué fuentes se hicieron. */}
                    Fuentes:{' '}
                    {search.providers && search.providers.length > 0
                      ? providersLabel(search.providers)
                      : 'no se registraban en búsquedas anteriores'}
                  </p>
                </div>
                <span className={`rounded-md px-2 py-0.5 text-xs ${status.className}`}>
                  {status.text}
                </span>
                <span className="text-xs tabular-nums text-slate-400">
                  {search.results_count} notas · {search.credits_used} crédito(s) ·{' '}
                  {formatUsd(search.llm_cost_usd)}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    reopen(search);
                  }}
                  className="rounded-lg bg-sky-500/20 px-3 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-500/30 focus-visible:outline-2 focus-visible:outline-sky-400"
                >
                  Abrir en el globo
                </button>
              </li>
            );
          })}
        </ul>
        {history.hasNextPage && (
          <button
            type="button"
            disabled={history.isFetchingNextPage}
            onClick={() => {
              void history.fetchNextPage();
            }}
            className="mt-4 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            {history.isFetchingNextPage ? 'Cargando…' : 'Ver más'}
          </button>
        )}
      </div>
    </div>
  );
}
