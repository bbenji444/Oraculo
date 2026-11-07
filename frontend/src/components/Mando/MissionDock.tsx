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
import { type CSSProperties, useEffect, useRef, useState } from 'react';

import { useConcepts } from '../../hooks/useConcepts';
import { useNow } from '../../hooks/useNow';
import { useSchedule } from '../../hooks/useSchedule';
import { useRegionDetail } from '../../hooks/useRegions';
import { useSearchHistory } from '../../hooks/useSearches';
import { isFinished, type Search, subdivisionsOf } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { type MissionSlot, useMandoStore } from '../../store/mando';
import { latestRun, stageProgress } from '../Explore/format';
import { RegionPicker } from '../Explore/RegionPicker';
import { DateRange } from '../Explore/SearchPanel';
import { SourceSwitches } from '../Explore/SourceSwitches';
import { useSearchLauncher } from '../Explore/useSearchLauncher';
import { CountUp } from '../ui/CountUp';
import { MissionProgress } from './MissionProgress';
import { TrackPicker } from './TrackPicker';
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
  trackNames,
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

// Ecos del radar: [ángulo desde el norte en grados, distancia al centro de 0 a
// 1]. Fijos y repartidos para que el barrido encienda uno cada tanto.
const SCOPE_BLIPS: readonly (readonly [number, number])[] = [
  [38, 0.62],
  [131, 0.38],
  [214, 0.74],
  [302, 0.5],
];

// Búsquedas recientes en la consola (además de la corrida): con más, las
// fichas ya no caben completas en un renglón.
const DOCK_RECENTS = 2;

// Color (RGB) de cada lámina del costo: los mismos tonos del expediente.
const COST_TONE = {
  queries: '0 210 255',
  free: '56 189 248',
  paid: '167 139 250',
  llm: '52 211 153',
} as const;

/** Si la tecla llegó mientras se escribe en un campo (no es un atajo). */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

/** Reloj de la Ciudad de México y cuenta regresiva a la próxima corrida. */
function MissionClock() {
  const now = useNow();
  const next = nextAutomaticRun(now, useSchedule().data?.upcoming);
  return (
    <div className="flex items-center gap-3 text-[11px] text-slate-400">
      <span className="mando-next-run">
        Próxima corrida automática <span className="text-slate-200">{next.time}</span> · en{' '}
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
  /** Lo que se lee al pasar el mouse, si la etiqueta es corta («Fuente»). */
  detail?: string;
  empty?: boolean;
}

/** Una parte de la frase: se toca para cambiarla. */
function Token({ slot, index, value, detail, empty = false }: TokenProps) {
  const open = useMandoStore((s) => s.slot === slot);
  const toggleSlot = useMandoStore((s) => s.toggleSlot);
  return (
    <button
      type="button"
      className="mando-token"
      aria-expanded={open}
      aria-controls="mando-editor"
      aria-label={`${SLOT_TITLE[slot]}: ${detail ?? value}. Cambiar`}
      title={detail}
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
  const subdivisionIds = useExplorerStore((s) => s.subdivisionIds);
  const regionId = useExplorerStore((s) => s.regionId);
  const range = useExplorerStore((s) => s.range);
  const concepts = useConcepts().data;
  const region = useRegionDetail(regionId).data;
  // «FGR · Homicidio» cuando la FGR va con subdivisiones (ADR-0038): el tema
  // general de cada subdivisión se llama como ella.
  const subdivisionNames = (concepts ?? [])
    .filter((c) => c.category_id !== null && subdivisionIds.includes(c.category_id))
    .map((c) => c.name);
  const names = trackNames(
    (concepts ?? []).filter((c) => conceptIds.includes(c.id)),
    subdivisionNames,
  );
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
        // Benji pidió que dijera solo «Fuente»; el detalle queda al pasar el mouse.
        value="Fuente"
        detail={
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
  // «Qué rastrear» es una ventana al centro: la FGR con sus subdivisiones y
  // los temas generales no caben en la tarjeta (Benji, 02/11/2026).
  if (slot === 'concepts') {
    return (
      <TrackPicker
        onClose={() => {
          setSlot(null);
        }}
      />
    );
  }
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

/** Una cifra del costo en su lámina; «—» mientras no hay consulta armada. */
function CostFigure({
  label,
  value,
  tone,
  format,
}: {
  label: string;
  value: number | undefined;
  tone: string;
  format?: (value: number) => string;
}) {
  return (
    <div className="mando-cost" style={{ '--tone': tone } as CSSProperties}>
      <dt className="mando-cost-label">{label}</dt>
      <dd className="mando-clock mando-cost-value">
        {value === undefined ? '—' : <CountUp value={value} format={format} />}
      </dd>
    </div>
  );
}

/** Lo que costaría la consulta, con cifras que corren al cambiar. */
function CostReadout({ launcher }: { launcher: Launcher }) {
  const { input, estimate, noSources } = launcher;
  const data = input ? estimate.data : undefined;
  let note: { text: string; alarm: boolean } | null = null;
  if (!input) {
    note = {
      text: noSources ? 'Enciende al menos una fuente.' : 'Falta elegir qué y dónde.',
      alarm: false,
    };
  } else if (estimate.error) {
    note = { text: estimate.error.message, alarm: true };
  } else if (!data) {
    note = { text: 'Calculando costo…', alarm: false };
  } else if (data.over_limit) {
    note = {
      text: `Se pasaría el tope mensual (${String(data.credits_month)} de ${String(data.credits_limit)}).`,
      alarm: true,
    };
  } else if (!data.llm.configured) {
    note = { text: 'Falta la llave de la IA en el servidor.', alarm: true };
  }
  return (
    <div aria-live="polite" className="space-y-1.5">
      <dl className="mando-cost-list">
        <CostFigure label="Consultas" value={data?.queries.length} tone={COST_TONE.queries} />
        {/* De pago en violeta: el naranja no va con la consola (Benji, 27/10/2026). */}
        <CostFigure
          label="Créditos"
          value={data?.credits}
          tone={data && data.credits > 0 ? COST_TONE.paid : COST_TONE.free}
        />
        <CostFigure
          label="IA máximo"
          value={data?.llm.max_cost_usd}
          tone={COST_TONE.llm}
          format={(value) => `$${value.toFixed(3)}`}
        />
      </dl>
      {note && (
        <p className={`text-[11px] leading-snug ${note.alarm ? 'text-rose-300' : 'text-sky-200'}`}>
          {note.text}
        </p>
      )}
    </div>
  );
}

function LaunchButton({ launcher }: { launcher: Launcher }) {
  const [shocks, setShocks] = useState<number[]>([]);
  const { input, start, busy, blocked } = launcher;
  return (
    <div className="mando-launch-wrap" data-ready={input && !blocked ? '' : undefined}>
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
        className="hud-btn hud-btn--solid w-full px-5 py-2 text-[11px]"
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
  const recents = recentMissions(items, DOCK_RECENTS);
  if (!run && recents.length === 0) return null;
  const reopen = (search: Search) => {
    restoreSearch({
      searchId: search.search_id,
      regionId: search.region_id,
      conceptIds: search.concepts.map((c) => c.id),
      dateFrom: search.date_from,
      dateTo: search.date_to,
      providers: search.providers,
      subdivisionIds: subdivisionsOf(search),
    });
  };
  return (
    // Un renglón propio a todo el ancho de la consola: antes compartía lugar
    // con el costo y las fichas se cortaban (Benji, 28/10/2026: «necesito que
    // todo aparezca completo»). Si no caben, bajan a otro renglón.
    <div className="mando-recents-row">
      <span
        className="hud-kpi-label shrink-0"
        title="Abre los resultados guardados de una corrida o de una búsqueda anterior, sin volver a buscar ni gastar"
      >
        Abrir resultados anteriores
      </span>
      <div className="mando-recents">
        {run && (
          <button
            type="button"
            onClick={() => {
              reopen(run);
            }}
            title="Abrir la última corrida del monitor automático"
            className="mando-recent mando-recent--run"
            style={{ '--i': 0 } as CSSProperties}
          >
            <span aria-hidden="true" className="hud-dot hud-dot--live" />
            <span>{runLabel(run)}</span>
          </button>
        )}
        {recents.map((search, index) => (
          <button
            key={search.search_id}
            type="button"
            onClick={() => {
              reopen(search);
            }}
            title={`Reabrir: ${search.concepts.map((c) => c.name).join(', ')} · ${search.region_name}`}
            className="mando-recent"
            style={{ '--i': index + 1 } as CSSProperties}
          >
            <span>{recentLabel(search)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Radar grande a la izquierda de la consola (Benji, 28/10/2026: «si quieres lo
 * del radar, hazlo en grande hasta la izquierda»). Es un adorno con estado:
 * barre despacio mientras se arma la consulta y más rápido, en verde, cuando ya
 * se puede lanzar. Los ecos se encienden justo cuando pasa el haz.
 */
function MissionScope({ ready }: { ready: boolean }) {
  return (
    <div className="mando-scope" data-ready={ready ? '' : undefined} aria-hidden="true">
      <div className="mando-scope-dish">
        <span className="mando-scope-sweep" />
        {SCOPE_BLIPS.map(([degrees, reach]) => (
          <span
            key={degrees}
            className="mando-scope-blip"
            style={
              {
                left: `${String(50 + 50 * reach * Math.sin((degrees * Math.PI) / 180))}%`,
                top: `${String(50 - 50 * reach * Math.cos((degrees * Math.PI) / 180))}%`,
                '--turn': degrees / 360,
              } as CSSProperties
            }
          />
        ))}
        <span className="mando-scope-core" />
      </div>
      <p className="mando-scope-label">{ready ? 'Listo para barrer' : 'Esperando orden'}</p>
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
      <section
        aria-label="Centro de mando"
        className={`${MANDO_GLASS} mando-dock mando-sweeping px-4 pb-3 pt-3`}
      >
        <span aria-hidden="true" className="mando-beam" />
        {/* Mientras busca, una franja de luz recorre la consola de lado a lado. */}
        <span aria-hidden="true" className="mando-scanline" />
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
            // El globo vuelve al Atlántico y gira mientras se arma la consulta.
            useExplorerStore.getState().showOverview();
          }}
          title="Cambiar qué, dónde, cuándo o fuentes y lanzar otra consulta"
          className="hud-btn hud-btn--sm"
        >
          Ajustar consulta
        </button>
        <button
          type="button"
          onClick={() => {
            useExplorerStore.getState().clearGlobe('atlantic');
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
      {/* Tres zonas que no se pisan: radar, la consulta y el lanzamiento. En
          una consola angosta el radar se oculta y el lanzamiento baja. */}
      <section
        aria-label="Centro de mando"
        className={`${MANDO_GLASS} mando-dock mando-console`}
        data-ready={launcher.input ? '' : undefined}
      >
        <span aria-hidden="true" className="mando-beam" />
        <span aria-hidden="true" className="mando-console-grid-bg" />
        <header className="mando-console-head">
          <span aria-hidden="true" className="hud-dot hud-dot--live" />
          <span className="mando-kicker whitespace-nowrap">
            Centro de mando · {editing ? 'Ajustar consulta' : 'Nueva consulta'}
          </span>
          <span className="ml-auto">
            <MissionClock />
          </span>
          {editing && (
            <button
              type="button"
              onClick={() => {
                useMandoStore.getState().setEditing(false);
              }}
              title="Volver a los resultados sin buscar de nuevo"
              className="hud-btn hud-btn--sm shrink-0 px-3 py-1 text-[11px]"
            >
              Volver
            </button>
          )}
          <MinimizeButton />
        </header>
        <div className="mando-console-grid">
          <MissionScope ready={Boolean(launcher.input) && !launcher.blocked} />
          <div className="min-w-0 self-center">
            {/* La frase se lee de un jalón, como una orden. */}
            <MissionSentence launcher={launcher} />
            {launcher.start.error && (
              <p className="mb-1 text-xs text-rose-300">{launcher.start.error.message}</p>
            )}
          </div>
          <div className="mando-console-launch">
            <CostReadout launcher={launcher} />
            <LaunchButton launcher={launcher} />
          </div>
        </div>
        {/* En celular no cabe: ahí la consola es solo la frase y el botón. */}
        <div className="mando-console-foot hidden sm:block">
          <RecentMissions />
        </div>
      </section>
    </>
  );
}
