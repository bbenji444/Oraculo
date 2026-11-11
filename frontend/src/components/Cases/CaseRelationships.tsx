/**
 * Pestaña «Vínculos» del detalle de un caso (Fase 9.5, decisiones D6 a D8).
 *
 * - Un filtro por estado: Por revisar, Confirmados y Descartados.
 * - Desde F12 (ADR-0107) cada estado se parte en dos grupos:
 *   - **Relaciones fuertes**: las dos entidades participan en el hecho de al
 *     menos una nota, o el vínculo lo dibujó una persona. Va abierto.
 *   - **Solo se mencionan juntas**: comparten notas, pero al menos una solo se
 *     nombra. Va plegado (nunca escondido para siempre, D4).
 * - «Ver vínculos de…» deja solo los de una entidad (la más conectada
 *   primero).
 * - Cada vínculo (`RelationshipItem`) dice por qué se relacionan.
 * - **Revisión en bloque** (F12): casilla en cada vínculo, en cada grupo y
 *   «todos»; la barra (`BulkBar`) confirma o descarta lo elegido de una vez.
 * - Quien puede editar dibuja vínculos nuevos entre entidades confirmadas
 *   («Nuevo vínculo»).
 *
 * No hace: no dibuja el muro sobre el globo (9.6).
 */
import { type ReactNode, useState } from 'react';

import { useCaseEntities } from '../../hooks/useEntities';
import {
  useCaseRelationships,
  useCreateRelationship,
  useReviewRelationship,
  useReviewRelationships,
} from '../../hooks/useRelationships';
import type { BulkAction, ReviewStatus } from '../../services/entities';
import type { Relationship } from '../../services/relationships';
import { BulkBar } from './BulkBar';
import { linkEnds, relationshipKey, splitByStrength, touches } from './grouping';
import { RelationshipForm } from './RelationshipForm';
import { RelationshipItem } from './RelationshipItem';
import { SelectBox } from './SelectBox';
import { bulkNotice, countLabel, selectionState, toggleKey, toggleKeys } from './selection';
import { HudSegmented } from '../ui/HudSegmented';
import { HudSelect } from '../ui/HudSelect';

const STATES: { value: ReviewStatus; label: string }[] = [
  { value: 'suggested', label: 'Por revisar' },
  { value: 'confirmed', label: 'Confirmados' },
  { value: 'discarded', label: 'Descartados' },
];

// Igual que en las entidades: lo confirmado solo se descarta y lo
// descartado solo se confirma.
const BULK_ACTIONS: Record<ReviewStatus, { confirm: boolean; discard: boolean }> = {
  suggested: { confirm: true, discard: true },
  confirmed: { confirm: false, discard: true },
  discarded: { confirm: true, discard: false },
};

// «Ver vínculos de…» sin entidad elegida (los ids de la base empiezan en 1).
const ALL_ENTITIES = 0;

interface CaseRelationshipsProps {
  caseId: string;
  canEdit: boolean;
}

export function CaseRelationships({ caseId, canEdit }: CaseRelationshipsProps) {
  const [tab, setTab] = useState<ReviewStatus>('suggested');
  const [drawing, setDrawing] = useState(false);
  const [showWeak, setShowWeak] = useState(false);
  const [focus, setFocus] = useState(ALL_ENTITIES);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const relationships = useCaseRelationships(caseId, tab);
  const confirmed = useCaseEntities(caseId, 'confirmed').data?.items ?? [];
  const review = useReviewRelationship(caseId);
  const bulk = useReviewRelationships(caseId);
  const create = useCreateRelationship(caseId);
  const data = relationships.data;
  const busy = review.isPending || create.isPending || bulk.isPending;
  const error = relationships.error ?? review.error ?? create.error ?? bulk.error;
  const items = data?.items ?? [];
  const ends = linkEnds(items);
  // Si la entidad elegida ya no tiene vínculos en este estado, se ven todos.
  const focusId = ends.some((e) => e.id === focus) ? focus : null;
  const { strong, weak } = splitByStrength(items.filter((r) => touches(r, focusId)));
  const shown = [...strong, ...weak];
  const shownKeys = shown.map(relationshipKey);
  const chosen = shown.filter((r) => selected.has(relationshipKey(r)));
  const actions = BULK_ACTIONS[tab];

  function changeTab(next: ReviewStatus) {
    setTab(next);
    setSelected(new Set());
    setNotice(null);
  }

  function runBulk(action: BulkAction) {
    setNotice(null);
    bulk.mutate(
      {
        action,
        items: chosen.map((r) => ({
          entity_a: r.entity_a.id,
          entity_b: r.entity_b.id,
          type: r.type,
        })),
      },
      {
        onSuccess: (result) => {
          setSelected(new Set());
          setNotice(bulkNotice(action, result));
        },
      },
    );
  }

  function groupBox(group: Relationship[], name: string) {
    if (!canEdit) return null;
    const keys = group.map(relationshipKey);
    return (
      <SelectBox
        state={selectionState(selected, keys)}
        label={`Elegir ${name} (${String(keys.length)})`}
        disabled={busy}
        onChange={() => {
          setSelected(toggleKeys(selected, keys));
        }}
      />
    );
  }

  function item(r: Relationship) {
    const key = relationshipKey(r);
    return (
      <RelationshipItem
        key={key}
        relationship={r}
        canEdit={canEdit}
        busy={busy}
        selected={selected.has(key)}
        onSelect={(checked) => {
          setSelected(toggleKey(selected, key, checked));
        }}
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
                changeTab('confirmed');
              },
            });
          }}
          onCancel={() => {
            setDrawing(false);
          }}
        />
      )}
      <div className="flex flex-wrap items-center gap-3 border-b border-sky-400/10 px-5 py-3">
        <HudSegmented
          label="Estado de los vínculos"
          value={tab}
          onChange={changeTab}
          options={STATES.map((s) => ({
            value: s.value,
            label: `${s.label} (${String(data?.counts[s.value] ?? 0)})`,
          }))}
        />
        {ends.length > 2 && (
          <span className="flex items-center gap-2 text-xs text-slate-400">
            <label htmlFor="vinculos-de">Ver vínculos de</label>
            <HudSelect
              id="vinculos-de"
              size="sm"
              className="w-auto max-w-[18rem] min-w-[10rem]"
              value={focusId ?? ALL_ENTITIES}
              options={[
                { value: ALL_ENTITIES, label: 'todas las entidades' },
                ...ends.map((e) => ({
                  value: e.id,
                  label: `${e.label} (${String(e.links)})`,
                })),
              ]}
              onChange={(value) => {
                setFocus(value);
                setSelected(new Set());
              }}
            />
          </span>
        )}
      </div>
      {canEdit && shown.length > 0 && (
        <div className="flex items-center gap-2 border-b border-sky-400/10 px-5 py-2 text-xs text-slate-200">
          <label className="flex cursor-pointer items-center gap-2">
            <SelectBox
              state={selectionState(selected, shownKeys)}
              label={`Elegir todos (${String(shownKeys.length)})`}
              disabled={busy}
              onChange={() => {
                setSelected(toggleKeys(selected, shownKeys));
              }}
            />
            Todos ({shownKeys.length})
          </label>
        </div>
      )}
      {canEdit && chosen.length > 0 && (
        <BulkBar
          count={countLabel(chosen.length, 'vínculo', 'vínculos')}
          discardedTab="Descartados"
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
          selectBox={groupBox(strong, 'las relaciones fuertes')}
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
          selectBox={groupBox(weak, 'las que solo se mencionan juntas')}
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
  /** Casilla para elegir el grupo completo (solo quien puede editar). */
  selectBox: ReactNode;
  children: ReactNode;
}

/**
 * Un grupo de vínculos con su explicación. Se puede elegir completo aunque
 * esté plegado: así se descartan de una vez los débiles sin abrirlos.
 */
function LinkGroup({ title, hint, open, onToggle, selectBox, children }: LinkGroupProps) {
  const heading = (
    <span className="font-display text-[11px] tracking-[0.16em] text-sky-100 uppercase">
      {title}
    </span>
  );
  return (
    <section aria-label={title} className="border-b border-sky-400/10 last:border-b-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-sky-400/[0.02] px-5 py-2">
        {selectBox}
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
