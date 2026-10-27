/**
 * Formulario de un concepto: crear o editar, con "Probar concepto" debajo.
 *
 * Los errores del backend se muestran junto a su campo; un nombre repetido
 * (409) se muestra en el campo nombre. Borrar pide confirmación.
 *
 * Diseño «consola táctica» (ADR-0036): panel con borde de luz, campos con aro
 * de enfoque y botones con destello.
 */
import { useId, useState } from 'react';

import { useCreateConcept, useDeleteConcept, useUpdateConcept } from '../../hooks/useConcepts';
import { ApiError } from '../../services/http';
import {
  type Concept,
  type ConceptInput,
  type FieldErrors,
  fieldErrors,
} from '../../services/concepts';
import { DeleteConfirm } from './DeleteConfirm';
import { KeywordChips } from './KeywordChips';
import { QueryPreview } from './QueryPreview';
import { DecodeText } from '../ui/DecodeText';
import { HudButton } from '../ui/HudButton';
import { HudPanel } from '../ui/HudPanel';

interface ConceptFormProps {
  /** Concepto a editar; sin él, se crea uno nuevo. */
  concept?: Concept;
  onSaved: (concept: Concept) => void;
  onClose: () => void;
}

// Colores que se distinguen bien entre sí sobre el mapa oscuro.
const PALETTE = [
  '#2E86DE',
  '#E74C3C',
  '#F39C12',
  '#9B59B6',
  '#1ABC9C',
  '#E84393',
  '#27AE60',
  '#D35400',
];

const EMPTY: ConceptInput = {
  name: '',
  description: '',
  keywords: [],
  exclude_terms: [],
  color: PALETTE[0] ?? '#2E86DE',
  is_active: true,
};

function toInput(concept: Concept | undefined): ConceptInput {
  if (!concept) return EMPTY;
  const { name, description, keywords, exclude_terms, color, is_active } = concept;
  return { name, description, keywords, exclude_terms, color, is_active };
}

function errorsFor(error: unknown): { fields: FieldErrors; general: string | null } {
  if (error instanceof ApiError && error.code === 'concept_name_taken') {
    return { fields: { name: [error.message] }, general: null };
  }
  const fields = fieldErrors(error);
  if (Object.keys(fields).length > 0) return { fields, general: null };
  return { fields: {}, general: error instanceof Error ? error.message : null };
}

export function ConceptForm({ concept, onSaved, onClose }: ConceptFormProps) {
  const [draft, setDraft] = useState<ConceptInput>(() => toInput(concept));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const create = useCreateConcept();
  const update = useUpdateConcept();
  const remove = useDeleteConcept();
  const id = useId();
  const saving = create.isPending || update.isPending;
  const { fields, general } = errorsFor(concept ? update.error : create.error);

  function set<K extends keyof ConceptInput>(key: K, value: ConceptInput[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function save(event: React.FormEvent) {
    event.preventDefault();
    if (concept) {
      update.mutate({ id: concept.id, patch: draft }, { onSuccess: onSaved });
    } else {
      create.mutate(draft, { onSuccess: onSaved });
    }
  }

  const inputClass = (invalid: boolean) => `hud-input ${invalid ? 'border-rose-500/70' : ''}`;

  return (
    <div className="space-y-4">
      <HudPanel className="hud-reveal p-5">
        <form onSubmit={save} aria-labelledby={`${id}-title`} className="space-y-5">
          <div className="flex items-center justify-between gap-3">
            <h2
              id={`${id}-title`}
              className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase"
            >
              <DecodeText text={concept ? `Editar «${concept.name}»` : 'Nuevo concepto'} />
            </h2>
            <button type="button" onClick={onClose} aria-label="Cerrar" className="hud-icon-btn">
              ×
            </button>
          </div>

          <div>
            <label htmlFor={`${id}-name`} className="hud-label">
              Nombre
            </label>
            <input
              id={`${id}-name`}
              value={draft.name}
              maxLength={80}
              aria-invalid={fields.name !== undefined}
              placeholder="Por ejemplo: Extorsión telefónica"
              onChange={(event) => {
                set('name', event.target.value);
              }}
              className={inputClass(fields.name !== undefined)}
            />
            {fields.name?.map((message) => (
              <p key={message} className="mt-1 text-xs text-rose-300">
                {message}
              </p>
            ))}
          </div>

          <div>
            <label htmlFor={`${id}-description`} className="hud-label">
              Descripción <span className="font-normal text-slate-500">(opcional)</span>
            </label>
            <textarea
              id={`${id}-description`}
              value={draft.description}
              maxLength={500}
              rows={2}
              onChange={(event) => {
                set('description', event.target.value);
              }}
              className={inputClass(fields.description !== undefined)}
            />
            {fields.description?.map((message) => (
              <p key={message} className="mt-1 text-xs text-rose-300">
                {message}
              </p>
            ))}
          </div>

          <KeywordChips
            label="Palabras clave"
            hint="Una nota entra si menciona cualquiera. Enter o coma para agregar; puedes pegar una lista."
            tone="keyword"
            terms={draft.keywords}
            errors={fields.keywords}
            onChange={(terms) => {
              set('keywords', terms);
            }}
          />
          <KeywordChips
            label="Exclusiones"
            hint="Una nota se descarta si menciona alguna, por ejemplo: curso, webinar, simulacro."
            tone="exclude"
            terms={draft.exclude_terms}
            errors={fields.exclude_terms}
            onChange={(terms) => {
              set('exclude_terms', terms);
            }}
          />

          <fieldset>
            <legend className="hud-label">Color en el mapa</legend>
            <div className="flex flex-wrap items-center gap-2">
              {PALETTE.map((color) => (
                <button
                  key={color}
                  type="button"
                  aria-label={`Color ${color}`}
                  aria-pressed={draft.color.toUpperCase() === color}
                  onClick={() => {
                    set('color', color);
                  }}
                  style={{ backgroundColor: color }}
                  className={`size-7 rounded-full ring-offset-2 ring-offset-slate-950 transition-transform duration-300 hover:scale-115 focus-visible:outline-2 focus-visible:outline-sky-400 ${
                    draft.color.toUpperCase() === color
                      ? 'scale-110 ring-2 ring-sky-200 shadow-[0_0_14px_rgb(0_210_255/0.5)]'
                      : ''
                  }`}
                />
              ))}
              <label className="flex items-center gap-2 text-xs text-slate-400">
                Otro:
                <input
                  type="color"
                  value={draft.color.toLowerCase()}
                  onChange={(event) => {
                    set('color', event.target.value.toUpperCase());
                  }}
                  className="h-7 w-10 cursor-pointer rounded border border-sky-400/30 bg-transparent"
                />
              </label>
            </div>
            {fields.color?.map((message) => (
              <p key={message} className="mt-1 text-xs text-rose-300">
                {message}
              </p>
            ))}
          </fieldset>

          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={draft.is_active}
              onChange={(event) => {
                set('is_active', event.target.checked);
              }}
              className="size-4 accent-sky-500"
            />
            Activo (aparece en el panel de búsqueda)
          </label>

          {general && (
            <p
              role="alert"
              className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
            >
              {general}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2 border-t border-sky-400/10 pt-5">
            <HudButton type="submit" variant="solid" disabled={saving}>
              {saving ? 'Guardando…' : concept ? 'Guardar cambios' : 'Crear concepto'}
            </HudButton>
            <HudButton variant="ghost" onClick={onClose}>
              Cancelar
            </HudButton>
            {concept && !confirmDelete && (
              <HudButton
                variant="danger"
                size="sm"
                className="ml-auto"
                onClick={() => {
                  setConfirmDelete(true);
                }}
              >
                Borrar
              </HudButton>
            )}
          </div>

          {concept && confirmDelete && (
            <DeleteConfirm
              name={concept.name}
              pending={remove.isPending}
              error={remove.error?.message ?? null}
              onCancel={() => {
                setConfirmDelete(false);
              }}
              onConfirm={() => {
                remove.mutate(concept.id, { onSuccess: onClose });
              }}
            />
          )}
        </form>
      </HudPanel>

      <QueryPreview draft={draft} />
    </div>
  );
}
