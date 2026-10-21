/**
 * Formulario para crear o editar un caso (Fase 9.3, historia H9.1).
 *
 * Nombre, descripción y sensibilidad. Los errores del servidor
 * (`invalid_case`) se muestran junto a su campo. Guardar llama al hook de
 * crear o de editar; quien lo usa decide qué hacer al terminar.
 *
 * No hace: no cierra ni archiva el caso (eso está en el detalle).
 */
import { useId, useState } from 'react';

import { useCreateCase, useUpdateCase } from '../../hooks/useCases';
import { type Case, type CaseInput, caseFieldErrors } from '../../services/cases';
import { SENSITIVITY_OPTIONS } from './labels';

interface CaseFormProps {
  /** Caso a editar; sin él, se crea uno nuevo. */
  editing?: Case;
  onSaved: (saved: Case) => void;
  onCancel: () => void;
}

const inputClass = (invalid: boolean) =>
  `w-full rounded-lg border bg-slate-950/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500/70 focus:outline-none ${
    invalid ? 'border-rose-500/70' : 'border-slate-700'
  }`;

export function CaseForm({ editing, onSaved, onCancel }: CaseFormProps) {
  const id = useId();
  const [form, setForm] = useState<CaseInput>({
    name: editing?.name ?? '',
    description: editing?.description ?? '',
    sensitivity: editing?.sensitivity ?? 'normal',
  });
  const create = useCreateCase();
  const update = useUpdateCase();
  const saving = create.isPending || update.isPending;
  const error = create.error ?? update.error;
  const fields = caseFieldErrors(error);

  function save(event: React.FormEvent) {
    event.preventDefault();
    if (editing) {
      update.mutate({ id: editing.id, patch: form }, { onSuccess: onSaved });
    } else {
      create.mutate(form, { onSuccess: onSaved });
    }
  }

  return (
    <form
      onSubmit={save}
      aria-labelledby={`${id}-title`}
      className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4"
    >
      <h2 id={`${id}-title`} className="text-base font-semibold text-slate-50">
        {editing ? 'Editar caso' : 'Nuevo caso'}
      </h2>
      <div>
        <label htmlFor={`${id}-name`} className="mb-1 block text-xs font-medium text-slate-300">
          Nombre
        </label>
        <input
          id={`${id}-name`}
          value={form.name}
          onChange={(event) => {
            setForm({ ...form, name: event.target.value });
          }}
          placeholder="Por ejemplo: Homicidio estilista Polanco"
          className={inputClass(fields.name !== undefined)}
        />
        {fields.name?.map((message) => (
          <p key={message} className="mt-1 text-xs text-rose-300">
            {message}
          </p>
        ))}
      </div>
      <div>
        <label
          htmlFor={`${id}-description`}
          className="mb-1 block text-xs font-medium text-slate-300"
        >
          Descripción <span className="font-normal text-slate-500">(opcional)</span>
        </label>
        <textarea
          id={`${id}-description`}
          rows={3}
          value={form.description}
          onChange={(event) => {
            setForm({ ...form, description: event.target.value });
          }}
          className={inputClass(fields.description !== undefined)}
        />
        {fields.description?.map((message) => (
          <p key={message} className="mt-1 text-xs text-rose-300">
            {message}
          </p>
        ))}
      </div>
      <div>
        <label
          htmlFor={`${id}-sensitivity`}
          className="mb-1 block text-xs font-medium text-slate-300"
        >
          Sensibilidad
        </label>
        <select
          id={`${id}-sensitivity`}
          value={form.sensitivity}
          onChange={(event) => {
            setForm({ ...form, sensitivity: event.target.value as CaseInput['sensitivity'] });
          }}
          className={inputClass(fields.sensitivity !== undefined)}
        >
          {SENSITIVITY_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-slate-500">
          Solo quienes son miembros del caso lo ven. La sensibilidad se muestra siempre junto a su
          nombre.
        </p>
      </div>
      {error && Object.keys(fields).length === 0 && (
        <p role="alert" className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {error.message}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 border-t border-slate-800 pt-4">
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 focus-visible:outline-2 focus-visible:outline-sky-300 disabled:opacity-50"
        >
          {saving ? 'Guardando…' : editing ? 'Guardar cambios' : 'Crear caso'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
