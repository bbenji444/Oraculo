/**
 * Formulario de un concepto: crear o editar, con "Probar concepto" debajo.
 *
 * Todo en una pantalla (ADR-0110): lo único obligatorio es escribir qué
 * noticias se quieren seguir. «Proponer frases con la IA» llena las frases
 * ahí mismo para revisarlas; si se guarda sin frases o sin nombre, la IA los
 * propone al guardar. Los nuevos se buscan «como en Google» (ADR-0109); los
 * exactos que ya existían (FGR, subdivisiones) se editan sin cambiar de modo.
 *
 * Los errores del backend se muestran junto a su campo; un nombre repetido
 * (409) se muestra en el campo nombre. Borrar pide confirmación.
 *
 * Diseño «consola táctica» (ADR-0036): panel con borde de luz, campos con aro
 * de enfoque y botones con destello.
 */
import { useId, useState } from 'react';

import {
  useCreateConcept,
  useDeleteConcept,
  useSuggestTerms,
  useUpdateConcept,
} from '../../hooks/useConcepts';
import { ApiError } from '../../services/http';
import {
  type Concept,
  type ConceptInput,
  type FieldErrors,
  type TermSuggestion,
  fieldErrors,
} from '../../services/concepts';
import { MODE_COPY, applySuggestion, fillMissing, needsProposal } from './conceptDraft';
import { DeleteConfirm } from './DeleteConfirm';
import { KeywordChips } from './KeywordChips';
import { QueryPreview } from './QueryPreview';
import { DecodeText } from '../ui/DecodeText';
import { HudButton } from '../ui/HudButton';
import { HudPanel } from '../ui/HudPanel';
import { Icon } from '../ui/Icon';
import { formatUsd } from '../Explore/format';

interface ConceptFormProps {
  /** Concepto a editar; sin él, se crea uno nuevo. */
  concept?: Concept;
  onSaved: (concept: Concept) => void;
  onClose: () => void;
  /**
   * Dentro de una ventana (Explorar): sin título ni «×» propios (los pone la
   * ventana) y sin «Probar concepto».
   */
  embedded?: boolean;
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

// Los conceptos nuevos se buscan «como en Google» (ADR-0109, D2).
const EMPTY: ConceptInput = {
  name: '',
  description: '',
  keywords: [],
  exclude_terms: [],
  color: PALETTE[0] ?? '#2E86DE',
  is_active: true,
  query_mode: 'open',
};

function toInput(concept: Concept | undefined): ConceptInput {
  if (!concept) return EMPTY;
  const { name, description, keywords, exclude_terms, color, is_active, query_mode } = concept;
  return { name, description, keywords, exclude_terms, color, is_active, query_mode };
}

function errorsFor(error: unknown): { fields: FieldErrors; general: string | null } {
  if (error instanceof ApiError && error.code === 'concept_name_taken') {
    return { fields: { name: [error.message] }, general: null };
  }
  const fields = fieldErrors(error);
  if (Object.keys(fields).length > 0) return { fields, general: null };
  return { fields: {}, general: error instanceof Error ? error.message : null };
}

export function ConceptForm({ concept, onSaved, onClose, embedded = false }: ConceptFormProps) {
  const [draft, setDraft] = useState<ConceptInput>(() => toInput(concept));
  const [proposal, setProposal] = useState<TermSuggestion | null>(null);
  const [missingIntent, setMissingIntent] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const create = useCreateConcept();
  const update = useUpdateConcept();
  const remove = useDeleteConcept();
  const suggest = useSuggestTerms();
  const id = useId();
  const saving = create.isPending || update.isPending || suggest.isPending;
  const { fields, general } = errorsFor(concept ? update.error : create.error);
  const suggestion = errorsFor(suggest.error);
  const copy = MODE_COPY[draft.query_mode];

  function set<K extends keyof ConceptInput>(key: K, value: ConceptInput[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function propose() {
    suggest.mutate(draft.description, {
      onSuccess: (proposed) => {
        setDraft((current) => applySuggestion(current, proposed));
        setProposal(proposed);
      },
    });
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const open = draft.query_mode === 'open';
    // Sin lo que se busca ni frases no hay qué buscar ni contra qué juzgar.
    if (open && draft.description.trim() === '' && draft.keywords.length === 0) {
      setMissingIntent(true);
      return;
    }
    let ready = draft;
    if (needsProposal(draft)) {
      let proposed: TermSuggestion;
      try {
        proposed = await suggest.mutateAsync(draft.description);
      } catch {
        return; // El error de la IA ya se muestra junto a la descripción.
      }
      ready = fillMissing(draft, proposed);
      setDraft(ready);
      setProposal(proposed);
    }
    if (concept) {
      update.mutate({ id: concept.id, patch: ready }, { onSuccess: onSaved });
    } else {
      create.mutate(ready, { onSuccess: onSaved });
    }
  }

  const inputClass = (invalid: boolean) => `hud-input ${invalid ? 'border-rose-500/70' : ''}`;
  const title = concept ? `Editar «${concept.name}»` : 'Nuevo concepto';
  // En una ventana, el título y el «×» los pone ella.
  const labelling = embedded ? { 'aria-label': title } : { 'aria-labelledby': `${id}-title` };
  const header = !embedded && (
    <div className="flex items-center justify-between gap-3">
      <h2
        id={`${id}-title`}
        className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase"
      >
        <DecodeText text={title} />
      </h2>
      <button type="button" onClick={onClose} aria-label="Cerrar" className="hud-icon-btn">
        <Icon name="close" className="text-lg" />
      </button>
    </div>
  );
  const descriptionErrors =
    fields.description ??
    suggestion.fields.description ??
    (missingIntent ? ['Escribe qué noticias quieres seguir.'] : undefined);
  const open = draft.query_mode === 'open';

  return (
    <div className="space-y-4">
      <Frame embedded={embedded}>
        <form
          onSubmit={(event) => {
            void save(event);
          }}
          {...labelling}
          className="space-y-5"
        >
          {header}

          {proposal && (
            <p
              role="status"
              className="rounded-lg border border-sky-400/20 bg-sky-400/[0.06] px-3 py-2 text-xs text-slate-200"
            >
              La IA propuso {proposal.keywords.length} frases ({formatUsd(proposal.cost_usd)}).
              Quita las que no sirvan o agrega otras antes de guardar.
            </p>
          )}

          {copy.explanation && <p className="text-xs text-slate-400">{copy.explanation}</p>}

          <div>
            <label htmlFor={`${id}-description`} className="hud-label">
              {copy.descriptionLabel}
            </label>
            <textarea
              id={`${id}-description`}
              value={draft.description}
              maxLength={500}
              rows={open ? 3 : 2}
              aria-invalid={descriptionErrors !== undefined}
              placeholder={
                open
                  ? 'Por ejemplo: robo de autos y camionetas con violencia en Jalisco'
                  : undefined
              }
              onChange={(event) => {
                set('description', event.target.value);
                setMissingIntent(false);
              }}
              className={inputClass(descriptionErrors !== undefined)}
            />
            <p className="mt-1 text-xs text-slate-500">{copy.descriptionHint}</p>
            {descriptionErrors?.map((message) => (
              <p key={message} className="mt-1 text-xs text-rose-300">
                {message}
              </p>
            ))}
            {open && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <HudButton
                  size="sm"
                  disabled={suggest.isPending || draft.description.trim() === ''}
                  onClick={propose}
                >
                  {suggest.isPending
                    ? 'La IA está pensando…'
                    : draft.keywords.length > 0
                      ? 'Volver a proponer frases'
                      : 'Proponer frases con la IA'}
                </HudButton>
                {draft.keywords.length > 0 && (
                  <span className="text-[11px] text-slate-500">
                    Reemplaza las frases y exclusiones de abajo.
                  </span>
                )}
              </div>
            )}
            {suggestion.general && (
              <p role="alert" className="mt-1 text-xs text-rose-300">
                {suggestion.general}
              </p>
            )}
          </div>

          <KeywordChips
            label={copy.keywordsLabel}
            hint={copy.keywordsHint}
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

          <div>
            <label htmlFor={`${id}-name`} className="hud-label">
              Nombre
            </label>
            <input
              id={`${id}-name`}
              value={draft.name}
              maxLength={80}
              aria-invalid={fields.name !== undefined}
              placeholder={
                open ? 'Si lo dejas vacío, la IA lo pone' : 'Por ejemplo: Extorsión telefónica'
              }
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
              {suggest.isPending
                ? 'La IA está pensando…'
                : saving
                  ? 'Guardando…'
                  : concept
                    ? 'Guardar cambios'
                    : 'Crear concepto'}
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
      </Frame>

      {!embedded && <QueryPreview draft={draft} />}
    </div>
  );
}

/** El panel del formulario; dentro de una ventana, la ventana ya es el panel. */
function Frame({ embedded, children }: { embedded: boolean; children: React.ReactNode }) {
  if (embedded) return <div>{children}</div>;
  return <HudPanel className="hud-reveal p-5">{children}</HudPanel>;
}
