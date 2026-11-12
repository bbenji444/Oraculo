/**
 * Pestaña «Entidades» del detalle de un caso (Fase 9.4, historia H9.2).
 *
 * - Avance de la IA ("Analizando con IA: 5 de 8 notas") y lo gastado; se
 *   actualiza solo mientras haya notas en la cola.
 * - "Analizar N notas pendientes" con su costo estimado, para las que ya
 *   estaban antes de la 9.4 o fallaron.
 * - Un filtro por estado: Por revisar, Confirmadas y Descartadas; solo lo
 *   confirmado llega al muro (9.6).
 * - Desde F12 (ADR-0107) cada estado se divide en grupos por tipo (Personas,
 *   Organizaciones, Vehículos…) que se pliegan, y dentro de cada grupo van
 *   primero las que participan en el hecho y después las que solo se nombran
 *   (`grouping.ts`).
 * - También desde F12, **revisión en bloque**: casilla en cada entidad y en
 *   cada grupo, «todas», «las que participan en el hecho» y «las que solo se
 *   nombran»; la barra (`BulkBar`) confirma o descarta lo elegido de una vez.
 *   Al confirmar, cada persona queda con el estatus que se ve en su renglón
 *   (D1). Las fusiones siguen par por par (D2).
 * - Desde la 9.5: «Posibles duplicados» para revisar lado a lado, y en cada
 *   tarjeta «Es la misma que…», «separar» y «Separar menciones».
 *
 * No hace: no dibuja vínculos (`CaseRelationships`).
 */
import { type ReactNode, useState } from 'react';

import {
  useAnalyzePending,
  useCaseEntities,
  useReviewEntities,
  useReviewEntity,
} from '../../hooks/useEntities';
import { useMergeSuggestions, useResolution } from '../../hooks/useResolution';
import type { BulkAction, Entity, LegalStatus, ReviewStatus } from '../../services/entities';
import { BulkBar } from './BulkBar';
import { EntityCard } from './EntityCard';
import { effectiveLegal, type EntityGroup, groupByType, participatesInEvent } from './grouping';
import { MergeSuggestions } from './MergeSuggestions';
import { SelectBox } from './SelectBox';
import {
  bulkDecisions,
  bulkNotice,
  countLabel,
  selectionState,
  selectionSummary,
  toggleKey,
  toggleKeys,
} from './selection';
import { HudSegmented } from '../ui/HudSegmented';

const STATES: { value: ReviewStatus; label: string }[] = [
  { value: 'suggested', label: 'Por revisar' },
  { value: 'confirmed', label: 'Confirmadas' },
  { value: 'discarded', label: 'Descartadas' },
];

// Qué se puede hacer en bloque en cada estado: lo confirmado solo se
// descarta y lo descartado solo se confirma (nada regresa a «sugerido»).
const BULK_ACTIONS: Record<ReviewStatus, { confirm: boolean; discard: boolean }> = {
  suggested: { confirm: true, discard: true },
  confirmed: { confirm: false, discard: true },
  discarded: { confirm: true, discard: false },
};

interface CaseEntitiesProps {
  caseId: string;
  canEdit: boolean;
}

/** "0.0038 USD". */
function usd(value: number): string {
  return `${value.toFixed(4)} USD`;
}

export function CaseEntities({ caseId, canEdit }: CaseEntitiesProps) {
  const [tab, setTab] = useState<ReviewStatus>('suggested');
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [legalChoice, setLegalChoice] = useState<ReadonlyMap<number, LegalStatus>>(new Map());
  const [notice, setNotice] = useState<string | null>(null);
  const entities = useCaseEntities(caseId, tab);
  const analyze = useAnalyzePending(caseId);
  const review = useReviewEntity(caseId);
  const bulk = useReviewEntities(caseId);
  const data = entities.data;
  const analysis = data?.analysis;
  const pending = analysis ? analysis.pending + analysis.failed : 0;
  const suggestions = useMergeSuggestions(caseId);
  const resolution = useResolution(caseId);
  // Destinos de «Es la misma que…»: sugeridas y confirmadas (lo más común es
  // unir una sugerida nueva a una persona ya confirmada).
  const suggested = useCaseEntities(caseId, 'suggested').data?.items ?? [];
  const confirmed = useCaseEntities(caseId, 'confirmed').data?.items ?? [];
  const busy = review.isPending || resolution.isPending || bulk.isPending;
  const error = entities.error ?? analyze.error ?? review.error ?? resolution.error ?? bulk.error;
  const groups = groupByType(data?.items ?? []);
  // En el orden de la pantalla, para que el resumen se lea igual que la lista.
  const shown = groups.flatMap((g) => g.items);
  const shownIds = shown.map((e) => e.id);
  const chosen = shown.filter((e) => selected.has(e.id));
  const inEventIds = shown.filter(participatesInEvent).map((e) => e.id);
  const onlyNamedIds = shown.filter((e) => !participatesInEvent(e)).map((e) => e.id);
  const actions = BULK_ACTIONS[tab];

  function changeTab(next: ReviewStatus) {
    setTab(next);
    setSelected(new Set());
    setNotice(null);
  }

  function toggleGroup(type: string) {
    const next = new Set(collapsed);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    setCollapsed(next);
  }

  function legalFor(entity: Entity): LegalStatus {
    return legalChoice.get(entity.id) ?? effectiveLegal(entity) ?? 'mentioned';
  }

  function runBulk(action: BulkAction) {
    setNotice(null);
    bulk.mutate(
      { action, items: bulkDecisions(chosen, action, legalChoice) },
      {
        onSuccess: (result) => {
          setSelected(new Set());
          setNotice(bulkNotice(action, result));
        },
      },
    );
  }

  function targetsFor(entity: Entity): Entity[] {
    return [...confirmed, ...suggested].filter(
      (other) => other.id !== entity.id && other.type === entity.type,
    );
  }

  function card(entity: Entity) {
    return (
      <EntityCard
        key={entity.id}
        entity={entity}
        canEdit={canEdit}
        busy={busy}
        legal={legalFor(entity)}
        onLegalChange={(legal) => {
          setLegalChoice(new Map(legalChoice).set(entity.id, legal));
        }}
        selected={selected.has(entity.id)}
        onSelect={(checked) => {
          setSelected(toggleKey(selected, entity.id, checked));
        }}
        mergeTargets={targetsFor(entity)}
        onResolve={(action) => {
          resolution.mutate(action);
        }}
        onConfirm={(legal) => {
          review.mutate({ entityId: entity.id, action: 'confirm', legal });
        }}
        onDiscard={() => {
          review.mutate({ entityId: entity.id, action: 'discard' });
        }}
      />
    );
  }

  return (
    <div className="hud-panel hud-spot hud-reveal overflow-hidden">
      <div className="hud-section-head">
        <h3 className="hud-section-title">Entidades</h3>
        {analysis && (
          <p aria-live="polite" className="text-xs text-slate-400">
            {analysis.queued > 0
              ? `Analizando con IA: ${String(analysis.done)} de ${String(analysis.articles)} notas…`
              : `IA: ${String(analysis.done)} de ${String(analysis.articles)} notas leídas`}
            {` · ${usd(analysis.cost_usd)}`}
            {analysis.title_snippet > 0 &&
              ` · ${String(analysis.title_snippet)} solo con título y fragmento`}
          </p>
        )}
      </div>
      {canEdit && pending > 0 && analysis?.queued === 0 && (
        <div className="flex flex-wrap items-center gap-3 border-b border-sky-400/10 bg-sky-400/[0.03] px-5 py-2.5 text-xs text-slate-300">
          <span>
            {pending} {pending === 1 ? 'nota sin analizar' : 'notas sin analizar'} (~
            {usd(analysis.estimated_pending_cost_usd)})
          </span>
          <button
            type="button"
            disabled={analyze.isPending}
            onClick={() => {
              analyze.mutate();
            }}
            className="hud-btn hud-btn--solid hud-btn--sm"
          >
            Analizar con IA
          </button>
        </div>
      )}
      <MergeSuggestions
        suggestions={suggestions.data ?? []}
        canEdit={canEdit}
        busy={busy}
        onDecide={(action) => {
          resolution.mutate(action);
        }}
      />
      <div className="flex flex-wrap items-center gap-3 border-b border-sky-400/10 px-5 py-3">
        <HudSegmented
          label="Estado de las entidades"
          value={tab}
          onChange={changeTab}
          options={STATES.map((s) => ({
            value: s.value,
            label: `${s.label} (${String(data?.counts[s.value] ?? 0)})`,
          }))}
        />
        {tab === 'suggested' && groups.length > 0 && (
          <p className="text-xs text-slate-400">
            Primero las que participan en el hecho; al final de cada grupo, las que solo se nombran.
          </p>
        )}
      </div>
      {canEdit && shown.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-sky-400/10 px-5 py-2 text-xs text-slate-400">
          <label className="flex cursor-pointer items-center gap-2 text-slate-200">
            <SelectBox
              state={selectionState(selected, shownIds)}
              label={`Elegir todas (${String(shownIds.length)})`}
              disabled={busy}
              onChange={() => {
                setSelected(toggleKeys(selected, shownIds));
              }}
            />
            Todas ({shownIds.length})
          </label>
          {inEventIds.length > 0 && onlyNamedIds.length > 0 && (
            <>
              <span aria-hidden="true">·</span>
              <span>Elegir solo:</span>
              <QuickPick
                disabled={busy}
                onPick={() => {
                  setSelected(new Set(inEventIds));
                }}
              >
                las que participan en el hecho ({inEventIds.length})
              </QuickPick>
              <QuickPick
                disabled={busy}
                onPick={() => {
                  setSelected(new Set(onlyNamedIds));
                }}
              >
                las que solo se nombran ({onlyNamedIds.length})
              </QuickPick>
            </>
          )}
        </div>
      )}
      {canEdit && chosen.length > 0 && (
        <BulkBar
          count={countLabel(chosen.length, 'entidad', 'entidades')}
          detail={selectionSummary(chosen)}
          confirmHint={
            chosen.some((e) => e.type === 'person')
              ? 'Cada persona queda con el estatus legal que ves en su renglón; cámbialo ahí antes si hace falta.'
              : undefined
          }
          canConfirm={actions.confirm}
          canDiscard={actions.discard}
          busy={busy}
          onConfirm={() => {
            runBulk('confirm');
          }}
          onDiscard={() => {
            runBulk('discard');
          }}
          onClear={() => {
            setSelected(new Set());
          }}
        />
      )}
      {notice && (
        <p role="status" className="border-b border-sky-400/10 px-5 py-2 text-xs text-emerald-200">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="px-4 pt-2 text-xs text-rose-300">
          {error.message}
        </p>
      )}
      {entities.isPending && <p className="p-4 text-sm text-slate-400">Cargando entidades…</p>}
      {data?.items.length === 0 && (
        <p className="p-4 text-sm text-slate-400">
          {tab === 'suggested'
            ? 'No hay nada por revisar. Al agregar noticias, la IA propone las personas, organizaciones, lugares y vehículos que mencionan.'
            : 'Nada por aquí todavía.'}
        </p>
      )}
      {groups.map((group) => (
        <EntityGroupSection
          key={group.type}
          group={group}
          open={!collapsed.has(group.type)}
          onToggle={() => {
            toggleGroup(group.type);
          }}
          selectBox={
            canEdit ? (
              <SelectBox
                state={selectionState(
                  selected,
                  group.items.map((e) => e.id),
                )}
                label={`Elegir ${group.label.toLowerCase()} (${String(group.items.length)})`}
                disabled={busy}
                onChange={() => {
                  setSelected(
                    toggleKeys(
                      selected,
                      group.items.map((e) => e.id),
                    ),
                  );
                }}
              />
            ) : null
          }
          renderCard={card}
        />
      ))}
    </div>
  );
}

/** Un atajo de selección que se lee como enlace («las que participan…»). */
function QuickPick({
  children,
  disabled,
  onPick,
}: {
  children: ReactNode;
  disabled: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onPick}
      className="text-sky-300 underline-offset-2 hover:underline disabled:text-slate-500"
    >
      {children}
    </button>
  );
}

interface EntityGroupSectionProps {
  group: EntityGroup;
  open: boolean;
  onToggle: () => void;
  /** Casilla para elegir el grupo completo (solo quien puede editar). */
  selectBox: ReactNode;
  renderCard: (entity: Entity) => ReactNode;
}

/**
 * Un grupo plegable («Personas · 5 · 3 participan en el hecho») con sus
 * tarjetas; una línea separa a las que solo se nombran.
 */
function EntityGroupSection({
  group,
  open,
  onToggle,
  selectBox,
  renderCard,
}: EntityGroupSectionProps) {
  const inEvent = group.items.filter(participatesInEvent);
  const onlyNamed = group.items.filter((e) => !participatesInEvent(e));
  const listId = `grupo-${group.type}`;

  return (
    <section aria-label={group.label} className="border-b border-sky-400/10 last:border-b-0">
      <div className="flex items-center gap-3 bg-sky-400/[0.02] px-5 py-2">
        {selectBox}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={onToggle}
          className="flex items-center gap-2 font-display text-[11px] tracking-[0.16em] text-sky-100 uppercase focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          <span aria-hidden="true" className="text-sky-300">
            {open ? '▾' : '▸'}
          </span>
          {group.label} · {group.items.length}
        </button>
        {group.inEvent > 0 && (
          <span className="text-xs text-slate-400">
            {group.inEvent} {group.inEvent === 1 ? 'participa' : 'participan'} en el hecho
          </span>
        )}
      </div>
      {open && (
        <ul id={listId} className="divide-y divide-sky-400/10">
          {inEvent.map(renderCard)}
          {inEvent.length > 0 && onlyNamed.length > 0 && (
            <li className="px-5 py-1.5 text-[11px] tracking-[0.12em] text-slate-500 uppercase">
              Solo se nombran ({onlyNamed.length})
            </li>
          )}
          {onlyNamed.map(renderCard)}
        </ul>
      )}
    </section>
  );
}
