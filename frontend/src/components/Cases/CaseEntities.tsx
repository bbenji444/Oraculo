/**
 * Sección "Entidades" del detalle de un caso (Fase 9.4, historia H9.2).
 *
 * - Avance de la IA ("Analizando con IA: 5 de 8 notas") y lo gastado; se
 *   actualiza solo mientras haya notas en la cola.
 * - "Analizar N notas pendientes" con su costo estimado, para las que ya
 *   estaban antes de la 9.4 o fallaron.
 * - Pestañas Sugeridas, Confirmadas y Descartadas; solo lo confirmado llegará
 *   al muro (9.6).
 * - Desde la 9.5: «Posibles duplicados» para revisar lado a lado, y en cada
 *   tarjeta «Es la misma que…», «separar» y «Separar menciones».
 *
 * No hace: no dibuja vínculos (`CaseRelationships`).
 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { invalidateCaseEntities } from '../../hooks/caseKeys';
import { useAnalyzePending, useCaseEntities, useReviewEntity } from '../../hooks/useEntities';
import { useMergeSuggestions, useResolution } from '../../hooks/useResolution';
import type { Entity, ReviewStatus } from '../../services/entities';
import { EntityCard } from './EntityCard';
import { MergeSuggestions } from './MergeSuggestions';

const TABS: { value: ReviewStatus; label: string }[] = [
  { value: 'suggested', label: 'Sugeridas' },
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
  useRefreshWhenAnalysisEnds(caseId, analysis?.queued ?? 0);

  function targetsFor(entity: Entity): Entity[] {
    return [...confirmed, ...suggested].filter(
      (other) => other.id !== entity.id && other.type === entity.type,
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-100">Entidades</h3>
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
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 px-4 py-2 text-xs text-slate-300">
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
            className="rounded-lg bg-sky-600 px-2.5 py-1 font-medium text-white hover:bg-sky-500 disabled:opacity-50"
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
      <div role="tablist" aria-label="Estado de las entidades" className="flex gap-1 px-3 pt-2">
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => {
              setTab(t.value);
            }}
            className={`rounded-t-lg px-3 py-1.5 text-xs ${
              tab === t.value ? 'bg-slate-800 text-slate-50' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.label} ({data?.counts[t.value] ?? 0})
          </button>
        ))}
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
            ? 'No hay sugerencias. Al agregar noticias, la IA propone las personas, organizaciones, lugares y vehículos que mencionan.'
            : 'Nada por aquí todavía.'}
        </p>
      )}
      <ul className="divide-y divide-slate-800">
        {data?.items.map((entity) => (
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
        ))}
      </ul>
    </div>
  );
}

/**
 * Cuando la IA termina de leer las notas en cola, vuelve a pedir duplicados y
 * vínculos: las sugerencias nuevas pueden traer pares nuevos.
 */
function useRefreshWhenAnalysisEnds(caseId: string, queued: number): void {
  const client = useQueryClient();
  const before = useRef(queued);
  useEffect(() => {
    if (before.current > 0 && queued === 0) void invalidateCaseEntities(client, caseId);
    before.current = queued;
  }, [client, caseId, queued]);
}
