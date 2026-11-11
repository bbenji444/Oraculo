/**
 * Pestaña «Vínculos» del detalle de un caso (Fase 9.5, decisiones D6 a D8).
 *
 * - Un filtro por estado: Por revisar, Confirmados y Descartados.
 * - Desde F12 (ADR-0107) cada estado se parte en dos grupos:
 *   - **Relaciones fuertes**: las dos entidades participan en el hecho de al
 *     menos una nota, o el vínculo lo dibujó una persona. Va abierto.
 *   - **Solo se mencionan juntas**: comparten notas, pero al menos una solo se
 *     nombra. Va plegado (nunca escondido para siempre, D4).
 * - Cada vínculo (`RelationshipItem`) dice por qué se relacionan.
 * - Quien puede editar confirma o descarta los sugeridos y dibuja vínculos
 *   nuevos entre entidades confirmadas («Nuevo vínculo»).
 *
 * No hace: no dibuja el muro sobre el globo (9.6).
 */
import { type ReactNode, useState } from 'react';

import { useCaseEntities } from '../../hooks/useEntities';
import {
  useCaseRelationships,
  useCreateRelationship,
  useReviewRelationship,
} from '../../hooks/useRelationships';
import type { ReviewStatus } from '../../services/entities';
import type { Relationship } from '../../services/relationships';
import { relationshipKey, splitByStrength } from './grouping';
import { RelationshipForm } from './RelationshipForm';
import { RelationshipItem } from './RelationshipItem';
import { HudSegmented } from '../ui/HudSegmented';

const STATES: { value: ReviewStatus; label: string }[] = [
  { value: 'suggested', label: 'Por revisar' },
  { value: 'confirmed', label: 'Confirmados' },
  { value: 'discarded', label: 'Descartados' },
];

interface CaseRelationshipsProps {
  caseId: string;
  canEdit: boolean;
}

export function CaseRelationships({ caseId, canEdit }: CaseRelationshipsProps) {
  const [tab, setTab] = useState<ReviewStatus>('suggested');
  const [drawing, setDrawing] = useState(false);
  const [showWeak, setShowWeak] = useState(false);
  const relationships = useCaseRelationships(caseId, tab);
  const confirmed = useCaseEntities(caseId, 'confirmed').data?.items ?? [];
  const review = useReviewRelationship(caseId);
  const create = useCreateRelationship(caseId);
  const data = relationships.data;
  const busy = review.isPending || create.isPending;
  const error = relationships.error ?? review.error ?? create.error;
  const { strong, weak } = splitByStrength(data?.items ?? []);

  function item(r: Relationship) {
    return (
      <RelationshipItem
        key={relationshipKey(r)}
        relationship={r}
        canEdit={canEdit}
        busy={busy}
        onReview={(action) => {
          review.mutate({ relationship: r, action });
        }}
      />
    );
  }

  return (
    <div className="hud-panel hud-spot hud-reveal overflow-hidden">
      <div className="hud-section-head">
        <h3 className="hud-section-title">Vínculos</h3>
        {canEdit && !drawing && confirmed.length >= 2 && (
          <button
            type="button"
            onClick={() => {
              setDrawing(true);
            }}
            className="hud-btn hud-btn--solid hud-btn--sm"
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
      <div className="border-b border-sky-400/10 px-5 py-3">
        <HudSegmented
          label="Estado de los vínculos"
          value={tab}
          onChange={setTab}
          options={STATES.map((s) => ({
            value: s.value,
            label: `${s.label} (${String(data?.counts[s.value] ?? 0)})`,
          }))}
        />
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
            ? 'Nada por revisar. Cuando confirmes entidades que aparecen en las mismas notas, aquí se propone vincularlas.'
            : 'Nada por aquí todavía.'}
        </p>
      )}
      {strong.length > 0 && (
        <LinkGroup
          title={`Relaciones fuertes · ${String(strong.length)}`}
          hint="Las dos participan en el mismo hecho, o lo dibujó una persona."
          open
        >
          {strong.map(item)}
        </LinkGroup>
      )}
      {weak.length > 0 && (
        <LinkGroup
          title={`Solo se mencionan juntas · ${String(weak.length)}`}
          hint="Comparten notas, pero al menos una solo se nombra. Suelen servir menos."
          open={showWeak}
          onToggle={() => {
            setShowWeak(!showWeak);
          }}
        >
          {weak.map(item)}
        </LinkGroup>
      )}
    </div>
  );
}

interface LinkGroupProps {
  title: string;
  hint: string;
  open: boolean;
  /** Sin él, el grupo no se pliega. */
  onToggle?: () => void;
  children: ReactNode;
}

function LinkGroup({ title, hint, open, onToggle, children }: LinkGroupProps) {
  const heading = (
    <span className="font-display text-[11px] tracking-[0.16em] text-sky-100 uppercase">
      {title}
    </span>
  );
  return (
    <section aria-label={title} className="border-b border-sky-400/10 last:border-b-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-sky-400/[0.02] px-5 py-2">
        {onToggle ? (
          <button
            type="button"
            aria-expanded={open}
            onClick={onToggle}
            className="flex items-center gap-2 focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            <span aria-hidden="true" className="text-sky-300">
              {open ? '▾' : '▸'}
            </span>
            {heading}
          </button>
        ) : (
          heading
        )}
        <span className="text-xs text-slate-400">{hint}</span>
      </div>
      {open && <ul className="divide-y divide-sky-400/10">{children}</ul>}
    </section>
  );
}
