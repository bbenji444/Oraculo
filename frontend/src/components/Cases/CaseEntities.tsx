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
 * - Desde la 9.5: «Posibles duplicados» para revisar lado a lado, y en cada
 *   tarjeta «Es la misma que…», «separar» y «Separar menciones».
 *
 * No hace: no dibuja vínculos (`CaseRelationships`).
 */
import { type ReactNode, useState } from 'react';

import { useAnalyzePending, useCaseEntities, useReviewEntity } from '../../hooks/useEntities';
import { useMergeSuggestions, useResolution } from '../../hooks/useResolution';
import type { Entity, ReviewStatus } from '../../services/entities';
import { EntityCard } from './EntityCard';
import { type EntityGroup, groupByType, participatesInEvent } from './grouping';
import { MergeSuggestions } from './MergeSuggestions';
import { HudSegmented } from '../ui/HudSegmented';

const STATES: { value: ReviewStatus; label: string }[] = [
  { value: 'suggested', label: 'Por revisar' },
  { value: 'confirmed', label: 'Confirmadas' },
  { value: 'discarded', label: 'Descartadas' },
];

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
  const entities = useCaseEntities(caseId, tab);
  const analyze = useAnalyzePending(caseId);
  const review = useReviewEntity(caseId);
  const data = entities.data;
  const analysis = data?.analysis;
  const pending = analysis ? analysis.pending + analysis.failed : 0;
  const suggestions = useMergeSuggestions(caseId);
  const resolution = useResolution(caseId);
  // Destinos de «Es la misma que…»: sugeridas y confirmadas (lo más común es
  // unir una sugerida nueva a una persona ya confirmada).
  const suggested = useCaseEntities(caseId, 'suggested').data?.items ?? [];
  const confirmed = useCaseEntities(caseId, 'confirmed').data?.items ?? [];
  const busy = review.isPending || resolution.isPending;
  const error = entities.error ?? analyze.error ?? review.error ?? resolution.error;
  const groups = groupByType(data?.items ?? []);

  function targetsFor(entity: Entity): Entity[] {
    return [...confirmed, ...suggested].filter(
      (other) => other.id !== entity.id && other.type === entity.type,
    );
  }

  function toggleGroup(type: string) {
    const next = new Set(collapsed);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    setCollapsed(next);
  }

  function card(entity: Entity) {
    return (
      <EntityCard
        key={entity.id}
        entity={entity}
        canEdit={canEdit}
        busy={busy}
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
          onChange={setTab}
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
          renderCard={card}
        />
      ))}
    </div>
  );
}

interface EntityGroupSectionProps {
  group: EntityGroup;
  open: boolean;
  onToggle: () => void;
  renderCard: (entity: Entity) => ReactNode;
}

/**
 * Un grupo plegable («Personas · 5 · 3 participan en el hecho») con sus
 * tarjetas; una línea separa a las que solo se nombran.
 */
function EntityGroupSection({ group, open, onToggle, renderCard }: EntityGroupSectionProps) {
  const inEvent = group.items.filter(participatesInEvent);
  const onlyNamed = group.items.filter((e) => !participatesInEvent(e));
  const listId = `grupo-${group.type}`;

  return (
    <section aria-label={group.label} className="border-b border-sky-400/10 last:border-b-0">
      <div className="flex items-center gap-3 bg-sky-400/[0.02] px-5 py-2">
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
