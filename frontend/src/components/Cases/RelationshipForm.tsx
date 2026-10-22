/**
 * Formulario «Nuevo vínculo» de un caso (Fase 9.5, decisión D7).
 *
 * El analista elige dos entidades confirmadas, el tipo de vínculo (con su
 * sentido cuando importa: «A es dueño de B»), una etiqueta propia si es
 * «otro» y una nota. Lo que dibuja nace confirmado con su firma.
 *
 * No hace: no manda nada al servidor (avisa con `onCreate`); las reglas de
 * forma viven en `draftProblem` (`labels.ts`).
 */
import { type FormEvent, useState } from 'react';

import type { Entity } from '../../services/entities';
import type { RelationshipDraft, RelationshipType } from '../../services/relationships';
import { CUSTOM_LABEL_MAX_CHARS, draftProblem, RELATIONSHIP_TYPE_OPTIONS } from './labels';

interface RelationshipFormProps {
  entities: Entity[];
  busy: boolean;
  onCreate: (draft: RelationshipDraft) => void;
  onCancel: () => void;
}

const FIELD =
  'rounded-md border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100 focus-visible:outline-2 focus-visible:outline-sky-400';

const EMPTY: RelationshipDraft = {
  entityA: 0,
  entityB: 0,
  type: 'associate',
  customLabel: '',
  notes: '',
};

export function RelationshipForm({ entities, busy, onCreate, onCancel }: RelationshipFormProps) {
  const [draft, setDraft] = useState<RelationshipDraft>(EMPTY);
  const [tried, setTried] = useState(false);
  const problem = draftProblem(draft);
  const option = RELATIONSHIP_TYPE_OPTIONS.find((o) => o.value === draft.type);

  function submit(event: FormEvent) {
    event.preventDefault();
    setTried(true);
    if (problem) return;
    onCreate(draft);
    setDraft(EMPTY);
    setTried(false);
  }

  function entitySelect(field: 'entityA' | 'entityB', label: string) {
    return (
      <select
        aria-label={label}
        value={draft[field]}
        onChange={(event) => {
          setDraft({ ...draft, [field]: Number(event.target.value) });
        }}
        className={`${FIELD} max-w-[14rem]`}
      >
        <option value={0}>elige…</option>
        {entities.map((e) => (
          <option key={e.id} value={e.id}>
            {e.label} ({e.type_label})
          </option>
        ))}
      </select>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-2 border-b border-slate-800 px-4 py-3 text-xs">
      <p className="text-slate-400">
        Lo que dibujas queda confirmado con tu nombre. Solo se vinculan entidades confirmadas.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {entitySelect('entityA', 'Primera entidad')}
        <select
          aria-label="Tipo de vínculo"
          value={draft.type}
          onChange={(event) => {
            setDraft({ ...draft, type: event.target.value as RelationshipType });
          }}
          className={FIELD}
        >
          {RELATIONSHIP_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.directed ? `→ ${o.label} →` : o.label}
            </option>
          ))}
        </select>
        {entitySelect('entityB', 'Segunda entidad')}
      </div>
      {option?.directed && draft.type !== 'custom' && (
        <p className="text-slate-500">Se lee: la primera {option.label} la segunda.</p>
      )}
      {draft.type === 'custom' && (
        <input
          aria-label="Etiqueta del vínculo"
          placeholder="Ej. socio en el salón"
          maxLength={CUSTOM_LABEL_MAX_CHARS}
          value={draft.customLabel}
          onChange={(event) => {
            setDraft({ ...draft, customLabel: event.target.value });
          }}
          className={`${FIELD} w-full max-w-sm`}
        />
      )}
      <textarea
        aria-label="Nota del vínculo"
        placeholder="Nota (opcional): de dónde sale este vínculo"
        rows={2}
        value={draft.notes}
        onChange={(event) => {
          setDraft({ ...draft, notes: event.target.value });
        }}
        className={`${FIELD} w-full`}
      />
      {tried && problem && (
        <p role="alert" className="text-rose-300">
          {problem}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-sky-600 px-2.5 py-1 font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          Guardar vínculo
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-2.5 py-1 text-slate-300 hover:bg-slate-800"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
