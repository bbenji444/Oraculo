/**
 * Pantalla Historial (§14.1): las búsquedas anteriores de la persona, de la más
 * reciente a la más vieja, con su estado, notas y costo. "Abrir en el globo"
 * la vuelve a mostrar en Explorar sin gastar nada (las notas ya están
 * guardadas). «Eliminar» la quita del historial con confirmación y se puede
 * deshacer (27/10/2026): sus notas siguen en el sistema.
 *
 * Diseño «consola táctica» (ADR-0036): cifras arriba, y cada búsqueda en un
 * panel con borde de luz; las corridas automáticas llevan un radar. El texto
 * ocupa al menos 16 rem y los botones bajan de renglón si no caben: antes, en
 * pantallas angostas, el título se partía en una palabra por renglón.
 *
 * Cada persona ve solo sus búsquedas (ADR-0042; lo asegura la base con
 * seguridad por filas). Un superusuario ve las suyas y las corridas
 * automáticas, y con «Ver de todos» las de todos, con el nombre de quién la
 * lanzó.
 */
import { type CSSProperties, useCallback, useState } from 'react';

import { useMe } from '../../hooks/useAuth';
import { useDeleteSearch, useRestoreSearch, useSearchHistory } from '../../hooks/useSearches';
import { type HistoryScope, type Search, subdivisionsOf } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import {
  automaticRunLabel,
  formatMexicoCity,
  formatRange,
  formatUsd,
  providersLabel,
} from '../Explore/format';
import { ConfirmDelete } from '../ConfirmDelete';
import { UndoToast } from '../UndoToast';
import { CountUp } from '../ui/CountUp';
import { ArrowIcon, HudButton } from '../ui/HudButton';
import { type ChipTone, HudChip } from '../ui/HudChip';
import { HudPanel } from '../ui/HudPanel';
import { HudSwitch } from '../ui/HudSwitch';
import { SectionHeading } from '../ui/SectionHeading';

const STATUS_LABEL: Record<Search['status'], { text: string; tone: ChipTone; live?: boolean }> = {
  pending: { text: 'En cola', tone: 'slate' },
  running: { text: 'Corriendo', tone: 'cyan', live: true },
  completed: { text: 'Terminada', tone: 'green' },
  partial: { text: 'Parcial', tone: 'amber' },
  failed: { text: 'Falló', tone: 'rose' },
};

// Las entradas escalonadas se cortan aquí: una lista larga no debe tardar en aparecer.
const MAX_STAGGER = 12;
const COUNT = new Intl.NumberFormat('es-MX');

function reopen(search: Search) {
  useExplorerStore.getState().restoreSearch({
    searchId: search.search_id,
    regionId: search.region_id,
    conceptIds: search.concepts.map((c) => c.id),
    dateFrom: search.date_from,
    dateTo: search.date_to,
    providers: search.providers,
    subdivisionIds: subdivisionsOf(search),
  });
  window.location.hash = '#/explorar';
}

/** Lupa de una búsqueda hecha por una persona (las automáticas llevan radar). */
function SearchGlyph() {
  return (
    <span
      aria-hidden="true"
      className="grid size-10 flex-none place-items-center rounded-full border border-sky-400/30 text-sky-300"
    >
      <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor">
        <circle cx="9" cy="9" r="5.5" strokeWidth="1.6" />
        <path d="m13.5 13.5 3.5 3.5" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </span>
  );
}

interface SearchItemProps {
  search: Search;
  index: number;
  /** Con «Ver de todos»: mostrar quién la lanzó. */
  showOwner: boolean;
  deleting: boolean;
  onDelete: (search: Search) => void;
}

function SearchItem({ search, index, showOwner, deleting, onDelete }: SearchItemProps) {
  const status = STATUS_LABEL[search.status];
  const automatic = automaticRunLabel(search);
  return (
    <li className="hud-reveal" style={{ '--i': Math.min(index, MAX_STAGGER) } as CSSProperties}>
      <HudPanel
        className={`flex flex-wrap items-center gap-x-5 gap-y-3 px-5 py-4 ${
          automatic ? 'border-sky-400/35' : ''
        }`}
      >
        {automatic ? <span aria-hidden="true" className="hud-radar" /> : <SearchGlyph />}
        <div className="min-w-0 flex-1 basis-64">
          {automatic && (
            // Corrida del reloj (F12.8): la ven los superusuarios (ADR-0042).
            <p className="mb-1 font-display text-[10px] tracking-[0.24em] text-sky-300 uppercase">
              {automatic}
            </p>
          )}
          <p className="font-medium text-slate-50">
            {search.concepts.map((c) => c.name).join(', ')} · {search.region_name}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {formatRange(search.date_from, search.date_to)} · pedida el{' '}
            {formatMexicoCity(search.created_at)}
            {showOwner && search.user_id && !automatic && (
              <>
                {' '}
                por <span className="font-mono text-slate-300">{search.user_id}</span>
              </>
            )}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {/* Antes de F12.2 las búsquedas no guardaban con qué fuentes se hicieron. */}
            Fuentes:{' '}
            {search.providers && search.providers.length > 0
              ? providersLabel(search.providers)
              : 'no se registraban en búsquedas anteriores'}
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          <HudChip tone={status.tone} dot live={status.live}>
            {status.text}
          </HudChip>
          <span className="text-xs tabular-nums text-slate-400">
            <span className="font-display text-sm text-slate-100">{search.results_count}</span>{' '}
            notas · {search.credits_used} crédito(s) · {formatUsd(search.llm_cost_usd)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <HudButton
            size="sm"
            icon={<ArrowIcon />}
            onClick={() => {
              reopen(search);
            }}
          >
            Abrir en el globo
          </HudButton>
          <ConfirmDelete
            what="la búsqueda del historial"
            busy={deleting}
            onConfirm={() => {
              onDelete(search);
            }}
          />
        </div>
      </HudPanel>
    </li>
  );
}

export function HistoryPage() {
  const isSuperuser = useMe().data?.role === 'superuser';
  const [scope, setScope] = useState<HistoryScope>('mine');
  const history = useSearchHistory(isSuperuser ? scope : 'mine');
  const searches = history.data?.pages.flatMap((page) => page.items) ?? [];
  const remove = useDeleteSearch();
  const restore = useRestoreSearch();
  // La última que se quitó, para «Deshacer».
  const [removed, setRemoved] = useState<string | null>(null);
  const closeUndo = useCallback(() => {
    setRemoved(null);
  }, []);
  const removeSearch = (search: Search) => {
    remove.mutate(search.search_id, {
      onSuccess: () => {
        setRemoved(search.search_id);
        // Si estaba abierta en Explorar, el globo la suelta.
        if (useExplorerStore.getState().searchId === search.search_id) {
          useExplorerStore.getState().clearGlobe();
        }
      },
    });
  };
  const kpis = [
    { label: 'Búsquedas', value: searches.length },
    { label: 'Corridas automáticas', value: searches.filter((s) => automaticRunLabel(s)).length },
    { label: 'Notas encontradas', value: searches.reduce((sum, s) => sum + s.results_count, 0) },
  ];

  return (
    <div className="h-full overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <SectionHeading
          kicker="Bitácora de búsquedas"
          title="Historial de búsquedas"
          description="Reabrir una búsqueda no gasta créditos: sus notas ya están guardadas."
          actions={
            isSuperuser ? (
              <span className="flex items-center gap-2 text-sm text-slate-300">
                Ver de todos
                <HudSwitch
                  checked={scope === 'all'}
                  label="Ver las búsquedas de todos"
                  onChange={(all) => {
                    setScope(all ? 'all' : 'mine');
                  }}
                />
              </span>
            ) : undefined
          }
        />
        {searches.length > 0 && (
          <div className="mt-6 grid grid-cols-3 gap-2 sm:gap-3">
            {kpis.map((kpi, i) => (
              <HudPanel
                key={kpi.label}
                className="hud-reveal px-3 py-3 sm:px-5 sm:py-4"
                style={{ '--i': i } as CSSProperties}
              >
                <p className="hud-kpi-label">{kpi.label}</p>
                <CountUp
                  value={kpi.value}
                  // Con más páginas por cargar, la cifra es «al menos»: lleva «+».
                  format={(n) => `${COUNT.format(Math.round(n))}${history.hasNextPage ? '+' : ''}`}
                  className="hud-kpi-value mt-2 block text-lg sm:mt-3 sm:text-[1.6rem]"
                />
              </HudPanel>
            ))}
          </div>
        )}
        {history.isPending && <p className="mt-6 text-sm text-slate-400">Cargando…</p>}
        {history.error && <p className="mt-6 text-sm text-rose-300">{history.error.message}</p>}
        {history.isSuccess && searches.length === 0 && (
          <p className="mt-6 text-sm text-slate-400">Todavía no hay búsquedas.</p>
        )}
        <ul className="mt-6 space-y-3">
          {searches.map((search, index) => (
            <SearchItem
              key={search.search_id}
              search={search}
              index={index}
              showOwner={scope === 'all'}
              deleting={remove.isPending && remove.variables === search.search_id}
              onDelete={removeSearch}
            />
          ))}
        </ul>
        {remove.error && (
          <p role="alert" className="mt-3 text-sm text-rose-300">
            {remove.error.message}
          </p>
        )}
        {history.hasNextPage && (
          <HudButton
            className="mt-5"
            disabled={history.isFetchingNextPage}
            onClick={() => {
              void history.fetchNextPage();
            }}
          >
            {history.isFetchingNextPage ? 'Cargando…' : 'Ver más'}
          </HudButton>
        )}
      </div>
      {removed && (
        <UndoToast
          message="Se quitó la búsqueda del historial."
          busy={restore.isPending}
          onUndo={() => {
            restore.mutate(removed, { onSuccess: closeUndo });
          }}
          onClose={closeUndo}
        />
      )}
    </div>
  );
}
