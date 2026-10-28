/**
 * Centro de mando (diseño «Centro de mando», 27/10/2026): la búsqueda abajo
 * al centro, escrita como una orden que se lee de corrido:
 *
 *   Rastrear [01 FGR] en [02 Jalisco] durante [03 los últimos 7 días] vía [04 2 fuentes gratis]
 *
 * Cada parte entre corchetes se toca y sube una tarjeta para cambiarla (los
 * mismos controles del diseño 2). A la derecha, el costo estimado con cifras
 * que corren y el botón «Iniciar barrido» con aro de carga y onda expansiva.
 * Abajo, las consultas recientes y la última corrida automática para
 * reabrirlas sin costo, y arriba el reloj de la Ciudad de México con la cuenta
 * regresiva a la próxima corrida automática.
 *
 * La consola cambia según la consulta:
 * - sin búsqueda (o «Ajustar consulta»): la frase para armar la consulta;
 * - buscando: el avance por etapas (MissionProgress);
 * - con resultados: un renglón con la consulta activa, para que el globo y el
 *   expediente tengan espacio;
 * - minimizada: una pastilla.
 *
 * Atajos: «/» abre la región, Esc cierra la tarjeta abierta.
 *
 * No hace: no tiene reglas propias para lanzar; usa useSearchLauncher, igual
 * que el diseño 2.
 */
import { useEffect, useRef, useState } from 'react';

import { useConcepts } from '../../hooks/useConcepts';
import { useNow } from '../../hooks/useNow';
import { useRegionDetail } from '../../hooks/useRegions';
import { useSearchHistory } from '../../hooks/useSearches';
import { isFinished, type Search } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { type MissionSlot, useMandoStore } from '../../store/mando';
import { latestRun, stageProgress } from '../Explore/format';
import { RegionPicker } from '../Explore/RegionPicker';
import { ConceptChips, DateRange } from '../Explore/SearchPanel';
import { SourceSwitches } from '../Explore/SourceSwitches';
import { useSearchLauncher } from '../Explore/useSearchLauncher';
import { CountUp } from '../ui/CountUp';
import { MissionProgress } from './MissionProgress';
import { MANDO_GLASS } from './ui';
import {
  clockLabel,
  conceptsLabel,
  countdownLabel,
  missionLabel,
  nextAutomaticRun,
  rangeConnector,
  rangeLabel,
  recentLabel,
  recentMissions,
  runLabel,
  sourcesLabel,
} from './mission';

type Launcher = ReturnType<typeof useSearchLauncher>;

const SLOT_TITLE: Record<MissionSlot, string> = {
  concepts: 'Qué rastrear',
  region: 'Dónde',
  range: 'Cuándo',
  sources: 'Con qué fuentes',
};

// Ondas que se dejan en pantalla al lanzar varias veces seguidas.
const MAX_SHOCKS = 3;

/** Si la tecla llegó mientras se escribe en un campo (no es un atajo). */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

/** Reloj de la Ciudad de México y cuenta regresiva a la próxima corrida. */
function MissionClock() {
  const now = useNow();
  const next = nextAutomaticRun(now);
  return (
    <div className="flex items-center gap-3 text-[11px] text-slate-400">
      <span className="hidden lg:inline">
        Próxima corrida automática{' '}
        <span className="text-slate-200">{String(next.hour).padStart(2, '0')}:00</span> · en{' '}
        {countdownLabel(next.seconds)}
      </span>
      <span className="mando-clock" title="Hora de la Ciudad de México">
        {clockLabel(now)}
      </span>
      <span className="font-display text-[9px] tracking-[0.2em] text-slate-500">CDMX</span>
    </div>
  );
}

interface TokenProps {
  slot: MissionSlot;
  index: string;
  value: string;
  empty?: boolean;
}

/** Una parte de la frase: se toca para cambiarla. */
function Token({ slot, index, value, empty = false }: TokenProps) {
  const open = useMandoStore((s) => s.slot === slot);
  const toggleSlot = useMandoStore((s) => s.toggleSlot);
  return (
    <button
      type="button"
      className="mando-token"
      aria-expanded={open}
      aria-controls="mando-editor"
      aria-label={`${SLOT_TITLE[slot]}: ${value}. Cambiar`}
      data-empty={empty ? '' : undefined}
      onClick={() => {
        toggleSlot(slot);
      }}
    >
      <span aria-hidden="true" className="mando-token-index">
        {index}
      </span>
      {/* key: el valor nuevo entra con un destello. */}
      <span key={value} className="mando-token-value">
        {value}
      </span>
    </button>
  );
}

function MissionSentence({ launcher }: { launcher: Launcher }) {
  const conceptIds = useExplorerStore((s) => s.conceptIds);
  const regionId = useExplorerStore((s) => s.regionId);
  const range = useExplorerStore((s) => s.range);
  const concepts = useConcepts().data;
  const region = useRegionDetail(regionId).data;
  const names = (concepts ?? []).filter((c) => conceptIds.includes(c.id)).map((c) => c.name);
  const connector = rangeConnector(range);
  const regionName = regionId === null ? 'elige una región' : (region?.display_name ?? '…');
  return (
    <p className="mando-sentence">
      Rastrear{' '}
      <Token slot="concepts" index="01" value={conceptsLabel(names)} empty={names.length === 0} />{' '}
      en <Token slot="region" index="02" value={regionName} empty={regionId === null} />{' '}
      {connector && `${connector} `}
      <Token slot="range" index="03" value={rangeLabel(range)} /> vía{' '}
      <Token
        slot="sources"
        index="04"
        value={
          launcher.sources.data
            ? sourcesLabel(launcher.sources.data, launcher.providers ?? [])
            : 'las fuentes de siempre'
        }
        empty={launcher.noSources}
      />
    </p>
  );
}

/** La tarjeta que sube de la consola para cambiar una parte de la consulta. */
function SlotEditor({ launcher }: { launcher: Launcher }) {
  const slot = useMandoStore((s) => s.slot);
  const setSlot = useMandoStore((s) => s.setSlot);
  const ref = useRef<HTMLDivElement>(null);

  // Al abrir la región, el cursor ya queda en el buscador.
  useEffect(() => {
    if (slot === 'region') ref.current?.querySelector<HTMLInputElement>('input')?.focus();
  }, [slot]);

  if (!slot) return null;
  return (
    <div
      key={slot}
      ref={ref}
      id="mando-editor"
      role="dialog"
      aria-label={`Ajustar la consulta: ${SLOT_TITLE[slot]}`}
      className={`${MANDO_GLASS} mando-editor space-y-3 p-4`}
    >
      <div className="flex items-center gap-2">
        <p className="mando-kicker">Ajustar · {SLOT_TITLE[slot]}</p>
        <button
          type="button"
          onClick={() => {
            setSlot(null);
          }}
          className="hud-btn hud-btn--sm ml-auto px-3 py-1 text-[11px]"
        >
          Listo
        </button>
      </div>
      {/* El desplazamiento va adentro: en el panel, las esquinas de mira
          (que salen 1 px) sacaban barras de desplazamiento. */}
      <div className="mando-editor-body" data-slot={slot}>
        {slot === 'concepts' && <ConceptChips />}
        {slot === 'region' && <RegionPicker />}
        {slot === 'range' && <DateRange />}
        {slot === 'sources' &&
          (launcher.sources.data ? (
            <SourceSwitches
              options={launcher.sources.data}
              chosen={launcher.providers ?? []}
              onChange={launcher.setSources}
            />
          ) : (
            <p className="text-[11px] text-slate-500">
              No se pudieron leer las fuentes; se buscará con las de por defecto.
            </p>
          ))}
      </div>
    </div>
  );
}

/** Lo que costaría la consulta, con cifras que corren al cambiar. */
function CostReadout({ launcher }: { launcher: Launcher }) {
  const { input, estimate, noSources } = launcher;
  if (!input) {
    return (
      <p className="max-w-[12rem] text-[11px] text-sky-200" aria-live="polite">
        {noSources ? 'Enciende al menos una fuente.' : 'Falta elegir qué y dónde.'}
      </p>
    );
  }
  if (estimate.error) {
    return <p className="max-w-[12rem] text-[11px] text-rose-300">{estimate.error.message}</p>;
  }
  if (!estimate.data) return <p className="text-[11px] text-slate-500">Calculando costo…</p>;
  const { credits } = estimate.data;
  return (
    <div aria-live="polite">
      <dl className="grid grid-cols-3 gap-4 text-right">
        <div>
          <dt className="hud-kpi-label">Consultas</dt>
          <dd className="mando-clock mt-1 text-[13px]">
            <CountUp value={estimate.data.queries.length} />
          </dd>
        </div>
        <div>
          <dt className="hud-kpi-label">Créditos</dt>
          {/* De pago en violeta: el naranja no va con la consola (Benji, 27/10/2026). */}
          <dd className={`mando-clock mt-1 text-[13px] ${credits > 0 ? 'text-violet-200' : ''}`}>
            <CountUp value={credits} />
          </dd>
        </div>
        <div>
          <dt className="hud-kpi-label">IA máx.</dt>
          <dd className="mando-clock mt-1 text-[13px]">
            <CountUp
              value={estimate.data.llm.max_cost_usd}
              format={(value) => `$${value.toFixed(3)}`}
            />
          </dd>
        </div>
      </dl>
      {estimate.data.over_limit && (
        <p className="mt-1 text-right text-[11px] text-rose-300">
          Se pasaría el tope mensual ({estimate.data.credits_month} de {estimate.data.credits_limit}
          ).
        </p>
      )}
      {!estimate.data.llm.configured && (
        <p className="mt-1 text-right text-[11px] text-rose-300">
          Falta la llave de la IA en el servidor.
        </p>
      )}
    </div>
  );
}

function LaunchButton({ launcher }: { launcher: Launcher }) {
  const [shocks, setShocks] = useState<number[]>([]);
  const { input, start, busy, blocked } = launcher;
  return (
    <div className="mando-launch-wrap">
      <span aria-hidden="true" className="mando-launch-ring" />
      <button
        type="button"
        disabled={blocked || busy}
        onClick={() => {
          if (!input) return;
          setShocks((current) => [...current.slice(1 - MAX_SHOCKS), Date.now()]);
          useMandoStore.getState().setEditing(false);
          start.mutate(input);
        }}
        className="hud-btn hud-btn--solid px-5 py-2.5 text-[11.5px]"
      >
        {busy ? 'Barrido en curso…' : 'Iniciar barrido ›'}
      </button>
      {shocks.map((id) => (
        <span key={id} aria-hidden="true" className="mando-shock" />
      ))}
    </div>
  );
}

/** Consultas recientes y la última corrida automática, para reabrirlas sin costo. */
function RecentMissions() {
  const history = useSearchHistory();
  const restoreSearch = useExplorerStore((s) => s.restoreSearch);
  const items = history.data?.pages.flatMap((page) => page.items) ?? [];
  const run = latestRun(items);
  const recents = recentMissions(items);
  if (!run && recents.length === 0) return null;
  const reopen = (search: Search) => {
    restoreSearch({
      searchId: search.search_id,
      regionId: search.region_id,
      conceptIds: search.concepts.map((c) => c.id),
      dateFrom: search.date_from,
      dateTo: search.date_to,
      providers: search.providers,
    });
  };
  return (
    // Un solo renglón: si no caben todas, las últimas se desvanecen en el borde.
    <div className="mando-recents flex min-w-0 flex-nowrap items-center gap-2">
      <span
        className="hud-kpi-label mr-1 shrink-0"
        title="Abre los resultados guardados de una corrida o de una búsqueda anterior, sin volver a buscar ni gastar"
      >
        Abrir resultados anteriores
      </span>
      {run && (
        <button
          type="button"
          onClick={() => {
            reopen(run);
          }}
          title="Abrir la última corrida del monitor automático"
          className="mando-recent border-sky-400/35"
        >
          <span aria-hidden="true" className="hud-radar size-4" />
          <span className="truncate">{runLabel(run)}</span>
        </button>
      )}
      {recents.map((search) => (
        <button
          key={search.search_id}
          type="button"
          onClick={() => {
            reopen(search);
          }}
          title={`Reabrir: ${search.concepts.map((c) => c.name).join(', ')} · ${search.region_name}`}
          className="mando-recent"
        >
          <span className="truncate">{recentLabel(search)}</span>
        </button>
      ))}
    </div>
  );
}

function MinimizeButton() {
  return (
    <button
      type="button"
      onClick={() => {
        useMandoStore.getState().setDockMinimized(true);
      }}
      title="Minimizar la consola para ver el globo completo"
      aria-label="Minimizar la consola"
      className="hud-icon-btn size-7 text-xs"
    >
      ▾
    </button>
  );
}

interface MissionDockProps {
  /** Si Explorar está a la vista: los atajos solo valen entonces. */
  active: boolean;
}

export function MissionDock({ active }: MissionDockProps) {
  const launcher = useSearchLauncher();
  const search = launcher.running;
  const finished = search !== undefined && isFinished(search.status);
  const editing = useMandoStore((s) => s.editing);
  const minimized = useMandoStore((s) => s.dockMinimized);
  const composing = !search || (finished && editing);

  // Atajos de la consola.
  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      const store = useMandoStore.getState();
      if (event.key === 'Escape' && store.slot) {
        store.setSlot(null);
        return;
      }
      if (event.key === '/' && !isTyping(event.target) && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        store.setDockMinimized(false);
        const current = launcher.running;
        if (current && isFinished(current.status)) store.setEditing(true);
        if (!current || isFinished(current.status)) store.setSlot('region');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [active, launcher.running]);

  if (minimized) {
    const percent =
      search && !finished
        ? ` · ${String(stageProgress(search.progress, search.status).percent)}%`
        : '';
    return (
      <div className="flex justify-center">
        <button
          type="button"
          onClick={() => {
            useMandoStore.getState().setDockMinimized(false);
          }}
          className="hud-btn hud-btn--sm mando-dock bg-[#050d12]/90 px-4"
        >
          ◈ Centro de mando{percent} ▴
        </button>
      </div>
    );
  }

  if (search && !finished) {
    return (
      <section aria-label="Centro de mando" className={`${MANDO_GLASS} mando-dock px-4 pb-3 pt-3`}>
        <span aria-hidden="true" className="mando-beam" />
        <header className="mb-3 flex items-center gap-3">
          <span aria-hidden="true" className="hud-dot hud-dot--live" />
          <span className="mando-kicker">Barrido en curso · {missionLabel(search)}</span>
          <span className="ml-auto">
            <MissionClock />
          </span>
          <MinimizeButton />
        </header>
        <MissionProgress search={search} />
      </section>
    );
  }

  if (search && !composing) {
    return (
      <section
        aria-label="Centro de mando"
        className={`${MANDO_GLASS} mando-dock flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2`}
      >
        <span aria-hidden="true" className="mando-beam" />
        <span aria-hidden="true" className="hud-dot hud-dot--live" />
        <span className="mando-kicker">Consulta activa</span>
        <p className="min-w-0 flex-1 truncate text-[13px] text-slate-100">
          {missionLabel(search)} · {search.results_count} notas
        </p>
        <button
          type="button"
          onClick={() => {
            useMandoStore.getState().setEditing(true);
          }}
          title="Cambiar qué, dónde, cuándo o fuentes y lanzar otra consulta"
          className="hud-btn hud-btn--sm"
        >
          Ajustar consulta
        </button>
        <button
          type="button"
          onClick={() => {
            useExplorerStore.getState().clearGlobe();
          }}
          title="Quitar los resultados del globo y armar otra consulta (esta queda en Historial)"
          className="hud-btn hud-btn--sm"
        >
          Nueva consulta
        </button>
        <MinimizeButton />
      </section>
    );
  }

  return (
    <>
      <SlotEditor launcher={launcher} />
      <section aria-label="Centro de mando" className={`${MANDO_GLASS} mando-dock px-4 pb-3 pt-3`}>
        <span aria-hidden="true" className="mando-beam" />
        <header className="flex items-center gap-3">
          <span aria-hidden="true" className="hud-dot hud-dot--live" />
          <span className="mando-kicker">
            Centro de mando · {editing ? 'Ajustar consulta' : 'Nueva consulta'}
          </span>
          <span className="ml-auto hidden shrink-0 text-[10.5px] text-slate-500 2xl:inline">
            <kbd className="mando-kbd">/</kbd> elegir región · <kbd className="mando-kbd">Esc</kbd>{' '}
            cerrar
          </span>
          <span className="ml-auto 2xl:ml-3">
            <MissionClock />
          </span>
          {editing && (
            <button
              type="button"
              onClick={() => {
                useMandoStore.getState().setEditing(false);
              }}
              title="Volver a los resultados sin buscar de nuevo"
              className="hud-btn hud-btn--sm px-3 py-1 text-[11px]"
            >
              Volver
            </button>
          )}
          <MinimizeButton />
        </header>
        {/* La frase a todo el ancho: se lee de un jalón, como una orden. */}
        <div className="mt-1">
          <MissionSentence launcher={launcher} />
        </div>
        {launcher.start.error && (
          <p className="mb-1 text-xs text-rose-300">{launcher.start.error.message}</p>
        )}
        <footer className="mt-1 flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-sky-400/10 pt-3">
          {/* En celular no caben: ahí la consola es solo la frase y el botón. */}
          <div className="hidden min-w-0 flex-1 sm:block">
            <RecentMissions />
          </div>
          <CostReadout launcher={launcher} />
          <LaunchButton launcher={launcher} />
        </footer>
      </section>
    </>
  );
}
