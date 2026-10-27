/**
 * Sección «Vínculos» del detalle de un caso (Fase 9.5, decisiones D6 a D8).
 *
 * - Pestañas Sugeridos, Confirmados y Descartados.
 * - Cada vínculo se lee en una línea («Julián N — aparecen juntas — Ramón
 *   Salas»), con el estatus legal de las personas siempre visible, su origen
 *   («aparecen en la misma nota» o «dibujado por una persona»), su confianza
 *   y las notas del caso que lo sostienen.
 * - Quien puede editar confirma o descarta los sugeridos y dibuja vínculos
 *   nuevos entre entidades confirmadas («Nuevo vínculo»).
 *
 * No hace: no dibuja el muro sobre el globo (9.6).
 */
import { useState } from 'react';

import { useCaseEntities } from '../../hooks/useEntities';
import {
  useCaseRelationships,
  useCreateRelationship,
  useReviewRelationship,
} from '../../hooks/useRelationships';
import type { ReviewStatus } from '../../services/entities';
import type { Relationship, RelationshipEnd } from '../../services/relationships';
import { formatDay } from '../Explore/format';
import { confidencePercent, relationshipPhrase } from './labels';
import { RelationshipForm } from './RelationshipForm';
import { ExternalLink } from '../ExternalLink';

const TABS: { value: ReviewStatus; label: string }[] = [
  { value: 'suggested', label: 'Sugeridos' },
  { value: 'confirmed', label: 'Confirmados' },
  { value: 'discarded', label: 'Descartados' },
];

const BUTTON =
  'rounded-lg px-2.5 py-1 text-xs font-medium focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50';

interface CaseRelationshipsProps {
  caseId: string;
  canEdit: boolean;
}

function End({ end }: { end: RelationshipEnd }) {
  return (
    <span className="text-slate-100">
      {end.label}
      {end.legal_status_label && (
        <span className="ml-1 text-[11px] font-medium text-amber-200">
          ({end.legal_status_label})
        </span>
      )}
    </span>
  );
}

function RelationshipItem({
  relationship,
  canEdit,
  busy,
  onReview,
}: {
  relationship: Relationship;
  canEdit: boolean;
  busy: boolean;
  onReview: (action: 'confirm' | 'discard') => void;
}) {
  const [open, setOpen] = useState(false);
  const notes = relationship.shared_articles.length;

  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1 text-sm">
          <p>
            <End end={relationship.entity_a} />
            <span className="mx-2 text-slate-400">{relationshipPhrase(relationship)}</span>
            <End end={relationship.entity_b} />
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {relationship.origin_label} · confianza {confidencePercent(relationship.confidence)}
            {notes > 0 && (
              <>
                {' · '}
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => {
                    setOpen(!open);
                  }}
                  className="text-sky-300 underline-offset-2 hover:underline"
                >
                  {notes} {notes === 1 ? 'nota en común' : 'notas en común'}
                </button>
              </>
            )}
            {relationship.reviewed_by &&
              ` · ${relationship.review_status_label} por ${relationship.reviewed_by}${
                relationship.reviewed_at ? ` el ${formatDay(relationship.reviewed_at)}` : ''
              }`}
          </p>
          {relationship.notes && (
            <p className="mt-1 text-xs text-slate-300">Nota: {relationship.notes}</p>
          )}
        </div>
        {canEdit && (
          <div className="flex shrink-0 gap-2">
            {relationship.review_status !== 'confirmed' && (
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  onReview('confirm');
                }}
                className={`${BUTTON} bg-emerald-500/20 text-emerald-100 hover:bg-emerald-500/30`}
              >
                Confirmar
              </button>
            )}
            {relationship.review_status !== 'discarded' && (
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  onReview('discard');
                }}
                className={`${BUTTON} text-rose-300 hover:bg-rose-500/10`}
              >
                Descartar
              </button>
            )}
          </div>
        )}
      </div>
      {open && (
        <ul className="mt-2 space-y-1 border-l border-slate-700 pl-3 text-xs">
          {relationship.shared_articles.map((a) => (
            <li key={a.article_id}>
              <ExternalLink href={a.url} className="text-sky-300 hover:underline">
                {a.title} ↗
              </ExternalLink>
              {a.published_at && (
                <span className="text-slate-400"> · {formatDay(a.published_at)}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function CaseRelationships({ caseId, canEdit }: CaseRelationshipsProps) {
  const [tab, setTab] = useState<ReviewStatus>('suggested');
  const [drawing, setDrawing] = useState(false);
  const relationships = useCaseRelationships(caseId, tab);
  const confirmed = useCaseEntities(caseId, 'confirmed').data?.items ?? [];
  const review = useReviewRelationship(caseId);
  const create = useCreateRelationship(caseId);
  const data = relationships.data;
  const busy = review.isPending || create.isPending;
  const error = relationships.error ?? review.error ?? create.error;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-100">Vínculos</h3>
        {canEdit && !drawing && confirmed.length >= 2 && (
          <button
            type="button"
            onClick={() => {
              setDrawing(true);
            }}
            className="rounded-lg bg-sky-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-sky-500"
          >
            Nuevo vínculo
          </button>
        )}
      </div>
      {drawing && (
        <RelationshipForm
          entities={confirmed}
          busy={busy}
          onCreate={(draft) => {
            create.mutate(draft, {
              onSuccess: () => {
                setDrawing(false);
                setTab('confirmed');
              },
            });
          }}
          onCancel={() => {
            setDrawing(false);
          }}
        />
      )}
      <div role="tablist" aria-label="Estado de los vínculos" className="flex gap-1 px-3 pt-2">
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
      {relationships.isPending && <p className="p-4 text-sm text-slate-400">Cargando vínculos…</p>}
      {data?.items.length === 0 && (
        <p className="p-4 text-sm text-slate-400">
          {tab === 'suggested'
            ? 'Sin sugerencias. Cuando confirmes entidades que aparecen en las mismas notas, aquí se propone vincularlas.'
            : 'Nada por aquí todavía.'}
        </p>
      )}
      <ul className="divide-y divide-slate-800">
        {data?.items.map((r) => (
          <RelationshipItem
            key={`${String(r.entity_a.id)}-${String(r.entity_b.id)}-${r.type}`}
            relationship={r}
            canEdit={canEdit}
            busy={busy}
            onReview={(action) => {
              review.mutate({ relationship: r, action });
            }}
          />
        ))}
      </ul>
    </div>
  );
}
