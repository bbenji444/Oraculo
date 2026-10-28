/**
 * Panel de búsqueda (§14.3): región, conceptos (chips, solo activos), rango de
 * fechas, fuentes (switches, F12.2: apagar SearchApi deja la búsqueda en 0
 * créditos), estimación ("2 consultas · hasta 3 créditos": SearchApi pide páginas
 * solo mientras vengan llenas), botón Buscar y barra de
 * avance por etapas.
 *
 * Lanzar gasta créditos y tokens: la estimación siempre se ve antes del botón,
 * y el botón se apaga si se pasaría el tope o falta la llave de la IA.
 *
 * Con una búsqueda terminada, el panel se reduce a tres renglones cortos (qué se
 * buscó, sus datos con «Editar» y «‹ Volver», y las descargas): así la
 * cronología de abajo tiene espacio. «Ocultar ‹» pliega solo la búsqueda a un
 * renglón; la cronología se pliega aparte con su propio botón (Benji,
 * 26/10/2026).
 */
import { type CSSProperties, useId, useState } from 'react';

import { useConcepts } from '../../hooks/useConcepts';
import { useSearch } from '../../hooks/useSearches';
import { isFinished } from '../../services/searches';
import { type RangeKind, useExplorerStore } from '../../store/explorer';
import { todayInMexico } from '../../ui/calendar';
import { HudDatePicker } from '../ui/HudDatePicker';
import { DownloadButtons } from './Controls';
import { formatRange, formatUsd, stageProgress } from './format';
import { RegionPicker } from './RegionPicker';
import { SourceSwitches } from './SourceSwitches';
import { GLASS, PANEL_TITLE, SMALL_BUTTON } from './ui';
import { useSearchLauncher } from './useSearchLauncher';

const RANGES: { kind: RangeKind; label: string }[] = [
  { kind: 'today', label: 'Hoy' },
  { kind: '7', label: '7 días' },
  { kind: '30', label: '30 días' },
  { kind: 'custom', label: 'Otro' },
];

/** Los conceptos activos como chips; también los usa el Centro de mando. */
export function ConceptChips() {
  const concepts = useConcepts().data?.filter((c) => c.is_active);
  const selected = useExplorerStore((s) => s.conceptIds);
  const toggle = useExplorerStore((s) => s.toggleConcept);
  if (!concepts) return <p className="text-xs text-slate-500">Cargando conceptos…</p>;
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Conceptos">
      {concepts.map((concept) => {
        const on = selected.includes(concept.id);
        return (
          <button
            key={concept.id}
            type="button"
            aria-pressed={on}
            onClick={() => {
              toggle(concept.id);
            }}
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-all duration-300 hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-sky-400 ${
              on
                ? 'border-sky-300/60 bg-sky-400/15 text-white shadow-[0_0_16px_rgb(0_210_255/0.3)]'
                : 'border-sky-400/15 bg-white/[0.03] text-slate-300 hover:border-sky-400/45 hover:bg-sky-400/[0.07]'
            }`}
          >
            <span
              aria-hidden="true"
              className="size-2 rounded-full"
              style={{ backgroundColor: concept.color, boxShadow: `0 0 8px ${concept.color}` }}
            />
            {concept.name}
          </button>
        );
      })}
    </div>
  );
}

/** Hoy, 7 días, 30 días u otro rango; también lo usa el Centro de mando. */
export function DateRange() {
  const range = useExplorerStore((s) => s.range);
  const setRange = useExplorerStore((s) => s.setRange);
  const rangeId = useId();
  const today = todayInMexico();
  return (
    <div className="space-y-2">
      <div
        className="hud-seg"
        role="group"
        aria-label="Rango de fechas"
        style={
          {
            '--seg-i': Math.max(
              0,
              RANGES.findIndex((item) => item.kind === range.kind),
            ),
            '--seg-n': RANGES.length,
          } as CSSProperties
        }
      >
        {RANGES.map((item) => (
          <button
            key={item.kind}
            type="button"
            aria-pressed={range.kind === item.kind}
            onClick={() => {
              setRange(item.kind === 'custom' ? { ...range, kind: 'custom' } : { kind: item.kind });
            }}
            className="focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            {item.label}
          </button>
        ))}
      </div>
      {range.kind === 'custom' && (
        <div className="hud-reveal grid grid-cols-2 gap-2">
          {(['from', 'to'] as const).map((field) => {
            const name = field === 'from' ? 'Desde' : 'Hasta';
            const id = `${rangeId}-${field}`;
            return (
              <div key={field}>
                <label htmlFor={id} className="hud-label mb-1.5 block">
                  {name}
                </label>
                {/* Calendario propio: el del navegador no toma el estilo. No
                    deja elegir días después de hoy ni un «hasta» antes del
                    «desde». */}
                <HudDatePicker
                  id={id}
                  label={name}
                  value={range[field]}
                  min={field === 'to' ? range.from : undefined}
                  max={field === 'from' ? (range.to ?? today) : today}
                  rangeFrom={range.from}
                  rangeTo={range.to}
                  onChange={(next) => {
                    setRange({ ...range, [field]: next });
                  }}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Progress({ searchId }: { searchId: string }) {
  const search = useSearch(searchId).data;
  if (!search) return null;
  const { label, percent } = stageProgress(search.progress, search.status);
  const failed = search.status === 'failed';
  return (
    <div className="space-y-1.5" aria-live="polite">
      <div className="flex items-center justify-between text-xs">
        <span className={failed ? 'text-rose-300' : 'text-slate-200'}>{label}</span>
        <span className="tabular-nums text-slate-400">{percent}%</span>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-sky-400/10"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Avance de la búsqueda"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-700 ${
            failed
              ? 'bg-rose-400'
              : `bg-gradient-to-r from-sky-600 to-cyan-300 shadow-[0_0_10px_rgb(0_210_255/0.6)] ${
                  isFinished(search.status) ? '' : 'hud-progress'
                }`
          }`}
          style={{ width: `${String(percent)}%` }}
        />
      </div>
      {isFinished(search.status) && (
        <p className="text-[11px] text-slate-400">
          {search.results_count} notas · {search.credits_used} crédito(s) ·{' '}
          {formatUsd(search.llm_cost_usd)}
        </p>
      )}
      {search.error_summary && <p className="text-[11px] text-amber-200">{search.error_summary}</p>}
    </div>
  );
}

/**
 * Pliega la búsqueda a un renglón. Solo la búsqueda: la cronología tiene su
 * propio botón para plegarse (Benji, 26/10/2026).
 */
function CollapseSearchButton() {
  const setSearchCollapsed = useExplorerStore((s) => s.setSearchCollapsed);
  return (
    <button
      type="button"
      onClick={() => {
        setSearchCollapsed(true);
      }}
      title="Ocultar la búsqueda (la cronología se queda)"
      className={`${SMALL_BUTTON} px-2 py-0.5 text-[11px]`}
    >
      Ocultar ‹
    </button>
  );
}

/** La búsqueda plegada: un renglón que la vuelve a abrir. */
function CollapsedSearch({ label }: { label: string }) {
  const setSearchCollapsed = useExplorerStore((s) => s.setSearchCollapsed);
  return (
    <button
      type="button"
      aria-label="Mostrar la búsqueda"
      onClick={() => {
        setSearchCollapsed(false);
      }}
      title="Mostrar la búsqueda"
      className={`${GLASS} hud-panel--interactive flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-100 focus-visible:outline-2 focus-visible:outline-sky-400`}
    >
      <span className={PANEL_TITLE}>Búsqueda</span>
      <span className="min-w-0 flex-1 truncate text-slate-400">{label}</span>
      <span aria-hidden="true" className="text-slate-400">
        ›
      </span>
    </button>
  );
}

/**
 * La búsqueda terminada, compacta: qué se buscó y sus botones en el primer
 * renglón, los datos en el segundo y las descargas en el tercero. Así la
 * cronología de abajo tiene más alto (Benji, 26/10/2026).
 */
function SearchSummary({ searchId, onEdit }: { searchId: string; onEdit: () => void }) {
  const search = useSearch(searchId).data;
  if (!search) return null;
  return (
    <section aria-label="Búsqueda" className={`${GLASS} space-y-1.5 px-3 py-2`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="min-w-0 truncate text-[13px] font-semibold text-slate-50">
          {search.concepts.map((c) => c.name).join(', ')} · {search.region_name}
        </h2>
        <CollapseSearchButton />
      </div>
      <div className="flex items-baseline gap-2 text-[11px]">
        <p className="min-w-0 flex-1 text-slate-400">
          {formatRange(search.date_from, search.date_to)} · {search.results_count} notas ·{' '}
          {/* Los créditos solo si se gastaron: las corridas automáticas siempre van en 0. */}
          {search.credits_used > 0 && `${String(search.credits_used)} crédito(s) · `}
          {formatUsd(search.llm_cost_usd)}
        </p>
        {/* Como links y no botones con borde: ocupan menos y se leen igual. */}
        <button
          type="button"
          onClick={onEdit}
          title="Cambiar región, conceptos o fechas"
          className="shrink-0 text-sky-300 hover:text-sky-100 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          Editar
        </button>
        <button
          type="button"
          onClick={() => {
            useExplorerStore.getState().clearGlobe();
          }}
          title="Quitar los resultados del globo y empezar otra búsqueda (esta queda en Historial)"
          className="shrink-0 text-sky-300 hover:text-sky-100 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          ‹ Volver
        </button>
      </div>
      <DownloadButtons searchId={searchId} />
    </section>
  );
}

export function SearchPanel() {
  const searchId = useExplorerStore((s) => s.searchId);
  const {
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
  } = useSearchLauncher();
  // Abierto para editar aunque haya una búsqueda terminada. ExplorePage
  // remonta el panel al cambiar de búsqueda, así que vuelve a empezar cerrado.
  const [editing, setEditing] = useState(false);
  const collapsed = useExplorerStore((s) => s.searchCollapsed);

  if (collapsed) {
    const label = running
      ? `${running.concepts.map((c) => c.name).join(', ')} · ${running.region_name}${
          busy ? ' · buscando…' : ''
        }`
      : 'Buscar noticias';
    return <CollapsedSearch label={label} />;
  }

  if (searchId && running && isFinished(running.status) && !editing) {
    return (
      <SearchSummary
        searchId={searchId}
        onEdit={() => {
          setEditing(true);
        }}
      />
    );
  }

  return (
    <section aria-label="Búsqueda" className={`${GLASS} space-y-4 p-4`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className={PANEL_TITLE}>Buscar noticias</h2>
        <div className="flex gap-1.5">
          {editing && (
            <button
              type="button"
              onClick={() => {
                setEditing(false);
              }}
              title="Volver a los resultados sin buscar de nuevo"
              className={`${SMALL_BUTTON} px-2 py-1 text-[11px]`}
            >
              Listo
            </button>
          )}
          <CollapseSearchButton />
        </div>
      </div>
      <RegionPicker />
      <div className="space-y-2">
        <p className="hud-label">Conceptos</p>
        <ConceptChips />
      </div>
      <DateRange />
      {sources.data && (
        <SourceSwitches options={sources.data} chosen={providers ?? []} onChange={setSources} />
      )}
      {sources.error && (
        <p className="text-[11px] text-slate-500">
          No se pudieron leer las fuentes; se buscará con las de por defecto.
        </p>
      )}
      <div className="text-xs" aria-live="polite">
        {!input && noSources && (
          <p className="text-amber-200">Enciende al menos una fuente para buscar.</p>
        )}
        {!input && !noSources && (
          <p className="text-slate-500">Elige región y al menos un concepto.</p>
        )}
        {input && estimate.isFetching && !estimate.data && (
          <p className="text-slate-500">Calculando costo…</p>
        )}
        {input && estimate.error && <p className="text-rose-300">{estimate.error.message}</p>}
        {input && estimate.data && (
          <p className="text-slate-300">
            {estimate.data.queries.length} consultas · hasta {estimate.data.credits} crédito(s) · IA
            máx. {formatUsd(estimate.data.llm.max_cost_usd)}
            {estimate.data.over_limit && (
              <span className="block text-amber-200">
                Se pasaría el tope mensual de créditos ({estimate.data.credits_month} de{' '}
                {estimate.data.credits_limit}).
              </span>
            )}
            {!estimate.data.llm.configured && (
              <span className="block text-amber-200">Falta la llave de la IA en el servidor.</span>
            )}
          </p>
        )}
      </div>
      <button
        type="button"
        disabled={blocked || busy}
        onClick={() => {
          if (input) start.mutate(input);
        }}
        className="hud-btn hud-btn--solid w-full py-3 text-xs"
      >
        {busy ? 'Buscando…' : 'Buscar'}
      </button>
      {start.error && <p className="text-xs text-rose-300">{start.error.message}</p>}
      {searchId && <Progress searchId={searchId} />}
    </section>
  );
}
