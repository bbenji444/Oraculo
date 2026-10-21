/**
 * «Posibles duplicados» de un caso (Fase 9.5, §9.8; ADR-0104).
 *
 * Un aviso con cuántos pares podrían ser la misma entidad; al abrirlo, cada
 * par se ve lado a lado con su motivo («mismo nombre», «nombre o alias en
 * común», «nombre parecido»), el estatus legal y las citas de cada una. Quien
 * puede editar elige cuál queda y decide «Son la misma» o «No son la misma».
 * El sistema nunca une solo.
 *
 * No hace: no pide datos ni decide (recibe la lista y avisa con `onDecide`).
 */
import { useState } from 'react';

import type { Entity } from '../../services/entities';
import type { MergeSuggestion } from '../../services/resolution';
import type { ResolutionAction } from '../../hooks/useResolution';
import { formatDay } from '../Explore/format';

interface MergeSuggestionsProps {
  suggestions: MergeSuggestion[];
  canEdit: boolean;
  busy: boolean;
  onDecide: (action: ResolutionAction) => void;
}

const BUTTON =
  'rounded-lg px-2.5 py-1 text-xs font-medium focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-50';

function legalText(entity: Entity): string | null {
  if (entity.type !== 'person') return null;
  if (entity.legal_status_label) return `Estatus: ${entity.legal_status_label}`;
  if (entity.suggested_legal_status_label) {
    return `Estatus sugerido: ${entity.suggested_legal_status_label}`;
  }
  return 'Estatus: la nota no lo dice';
}

function Side({ entity, keep }: { entity: Entity; keep: boolean }) {
  const legal = legalText(entity);
  return (
    <div
      className={`min-w-0 flex-1 rounded-lg border p-2 ${
        keep ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-slate-700'
      }`}
    >
      <p className="text-sm text-slate-100">
        {entity.label}
        <span className="ml-2 text-[11px] text-slate-400">{entity.review_status_label}</span>
      </p>
      {legal && <p className="text-xs font-medium text-amber-200">{legal}</p>}
      {entity.aliases.length > 0 && (
        <p className="text-xs text-slate-400">También: {entity.aliases.join(', ')}</p>
      )}
      <ul className="mt-1 space-y-1">
        {entity.mentions.map((m) => (
          <li key={m.id} className="text-xs text-slate-300">
            «{m.evidence_span}»
            <span className="text-slate-500">
              {' '}
              — {m.source_name ?? m.article_title}
              {m.published_at && `, ${formatDay(m.published_at)}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Pair({
  suggestion,
  canEdit,
  busy,
  onDecide,
}: {
  suggestion: MergeSuggestion;
  canEdit: boolean;
  busy: boolean;
  onDecide: (action: ResolutionAction) => void;
}) {
  const { first, second } = suggestion;
  const [keepId, setKeepId] = useState(suggestion.keep_id);
  const mergeId = keepId === first.id ? second.id : first.id;
  const name = `quedar-${String(first.id)}-${String(second.id)}`;

  return (
    <li className="space-y-2 px-4 py-3">
      <p className="text-xs text-slate-400">
        <span className="mr-2 rounded-md bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
          {first.type_label}
        </span>
        Posible duplicado: <span className="text-slate-200">{suggestion.reason_label}</span>
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Side entity={first} keep={keepId === first.id} />
        <Side entity={second} keep={keepId === second.id} />
      </div>
      {canEdit && (
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-300">
          <fieldset className="flex flex-wrap items-center gap-3">
            <legend className="sr-only">¿Cuál queda?</legend>
            <span>Queda:</span>
            {[first, second].map((entity) => (
              <label key={entity.id} className="flex items-center gap-1">
                <input
                  type="radio"
                  name={name}
                  checked={keepId === entity.id}
                  onChange={() => {
                    setKeepId(entity.id);
                  }}
                />
                {entity.label}
              </label>
            ))}
          </fieldset>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              onDecide({ kind: 'merge', keepId, mergeId });
            }}
            className={`${BUTTON} bg-emerald-500/20 text-emerald-100 hover:bg-emerald-500/30`}
          >
            Son la misma
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              onDecide({ kind: 'dismiss', firstId: first.id, secondId: second.id });
            }}
            className={`${BUTTON} text-slate-300 hover:bg-slate-800`}
          >
            No son la misma
          </button>
        </div>
      )}
    </li>
  );
}

export function MergeSuggestions({ suggestions, canEdit, busy, onDecide }: MergeSuggestionsProps) {
  const [open, setOpen] = useState(false);
  if (suggestions.length === 0) return null;
  const count = suggestions.length;

  return (
    <div className="border-b border-slate-800">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
        }}
        className="flex w-full items-center justify-between px-4 py-2 text-left text-xs text-amber-100 hover:bg-amber-500/5"
      >
        <span>
          {count} {count === 1 ? 'posible duplicado' : 'posibles duplicados'}: el sistema solo
          sugiere, tú decides.
        </span>
        <span className="text-sky-300">{open ? 'Ocultar' : 'Revisar'}</span>
      </button>
      {open && (
        <ul className="divide-y divide-slate-800 bg-slate-950/30">
          {suggestions.map((s) => (
            <Pair
              key={`${String(s.first.id)}-${String(s.second.id)}`}
              suggestion={s}
              canEdit={canEdit}
              busy={busy}
              onDecide={onDecide}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
