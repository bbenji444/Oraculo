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
import { HudSelect } from '../ui/HudSelect';

interface RelationshipFormProps {
  entities: Entity[];
  busy: boolean;
  onCreate: (draft: RelationshipDraft) => void;
  onCancel: () => void;
}

// Campo chico de la consola táctica (ADR-0036).
const FIELD = 'hud-input w-auto px-2 py-1.5 text-xs';

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
      <HudSelect
        label={label}
        size="sm"
        className="w-auto max-w-[14rem] min-w-[9rem]"
        value={draft[field]}
        options={[
          { value: 0, label: 'elige…' },
          ...entities.map((e) => ({ value: e.id, label: `${e.label} (${e.type_label})` })),
        ]}
        onChange={(next) => {
          setDraft({ ...draft, [field]: next });
        }}
      />
    );
  }

  return (
    <form
      onSubmit={submit}
      className="hud-reveal space-y-3 border-b border-sky-400/10 bg-sky-400/[0.03] px-5 py-4 text-xs"
    >
      <p className="text-slate-400">
        Lo que dibujas queda confirmado con tu nombre. Solo se vinculan entidades confirmadas.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {entitySelect('entityA', 'Primera entidad')}
        <HudSelect
          label="Tipo de vínculo"
          size="sm"
          className="w-auto min-w-[9rem]"
          value={draft.type}
          options={RELATIONSHIP_TYPE_OPTIONS.map((o) => ({
            value: o.value,
            label: o.directed ? `→ ${o.label} →` : o.label,
          }))}
          onChange={(next: RelationshipType) => {
            setDraft({ ...draft, type: next });
          }}
        />
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
        <button type="submit" disabled={busy} className="hud-btn hud-btn--solid hud-btn--sm">
          Guardar vínculo
        </button>
        <button type="button" onClick={onCancel} className="hud-btn hud-btn--ghost hud-btn--sm">
          Cancelar
        </button>
      </div>
    </form>
  );
}
