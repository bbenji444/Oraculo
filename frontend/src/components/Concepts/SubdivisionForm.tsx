/**
 * Editor de una subdivisión (Benji, 02/11/2026; ADR-0038).
 *
 * Arriba, la subdivisión: nombre, color, lo que debe entender la IA por ella
 * y si está prendida. Abajo, las palabras clave y exclusiones de su **tema
 * general**: con ellas se busca la subdivisión sola («Homicidio») o junto con
 * la FGR («FGR · Homicidio», que pide las dos palabras).
 *
 * Al guardar se manda solo lo que cambió: la subdivisión a `PATCH
 * /categories/{id}` y las palabras a `PATCH /concepts/{id}` del tema. Los
 * errores se muestran junto a su campo.
 *
 * No hace: no reclasifica notas; lo editado vale para las que se clasifiquen
 * después.
 */
import { useId, useState } from 'react';

import { useUpdateCategory } from '../../hooks/useCategories';
import { useUpdateConcept } from '../../hooks/useConcepts';
import { type Category, type CategoryPatch, categoryFieldErrors } from '../../services/categories';
import { type Concept, fieldErrors } from '../../services/concepts';
import { NO_CATEGORY_COLOR } from '../Explore/categoryColor';
import { DecodeText } from '../ui/DecodeText';
import { HudButton } from '../ui/HudButton';
import { HudPanel } from '../ui/HudPanel';
import { HudSwitch } from '../ui/HudSwitch';
import { KeywordChips } from './KeywordChips';

interface SubdivisionFormProps {
  category: Category;
  /** Su tema general, si tiene (de `/concepts`). */
  topic: Concept | undefined;
  onClose: () => void;
}

// Mismos topes que el servidor (domain/categories.py): la IA lee la
// descripción en cada lote.
const NAME_MAX = 60;
const DESCRIPTION_MAX = 400;

interface Draft {
  name: string;
  description: string;
  color: string;
  is_active: boolean;
  keywords: string[];
  exclude_terms: string[];
}

function toDraft(category: Category, topic: Concept | undefined): Draft {
  return {
    name: category.name,
    description: category.description,
    color: category.color ?? NO_CATEGORY_COLOR,
    is_active: category.is_active,
    keywords: topic?.keywords ?? [],
    exclude_terms: topic?.exclude_terms ?? [],
  };
}

function sameTerms(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((term, i) => term === b[i]);
}

export function SubdivisionForm({ category, topic, onClose }: SubdivisionFormProps) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(category, topic));
  const [saved, setSaved] = useState(false);
  const updateCategory = useUpdateCategory();
  const updateConcept = useUpdateConcept();
  const id = useId();
  const saving = updateCategory.isPending || updateConcept.isPending;
  const fields = categoryFieldErrors(updateCategory.error);
  const termFields = fieldErrors(updateConcept.error);
  // Un error que no es de un campo (la red, el servidor) va en un aviso general.
  let general: string | null = null;
  if (updateCategory.error && Object.keys(fields).length === 0) {
    general = updateCategory.error.message;
  } else if (updateConcept.error && Object.keys(termFields).length === 0) {
    general = updateConcept.error.message;
  }

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setSaved(false);
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const patch: CategoryPatch = {};
    if (draft.name !== category.name) patch.name = draft.name;
    if (draft.description !== category.description) patch.description = draft.description;
    if (draft.color !== (category.color ?? NO_CATEGORY_COLOR)) patch.color = draft.color;
    if (draft.is_active !== category.is_active) patch.is_active = draft.is_active;
    const termsChanged =
      topic !== undefined &&
      (!sameTerms(draft.keywords, topic.keywords) ||
        !sameTerms(draft.exclude_terms, topic.exclude_terms));
    try {
      if (Object.keys(patch).length > 0) {
        await updateCategory.mutateAsync({ id: category.id, patch });
      }
      if (topic && termsChanged) {
        await updateConcept.mutateAsync({
          id: topic.id,
          patch: { keywords: draft.keywords, exclude_terms: draft.exclude_terms },
        });
      }
      setSaved(true);
    } catch {
      // El error queda en la mutación y se muestra junto a su campo.
    }
  }

  const inputClass = (invalid: boolean) => `hud-input ${invalid ? 'border-rose-500/70' : ''}`;

  return (
    <HudPanel className="hud-reveal p-5">
      <form
        onSubmit={(event) => {
          void save(event);
        }}
        aria-labelledby={`${id}-title`}
        className="space-y-5"
      >
        <div className="flex items-center justify-between gap-3">
          <h2
            id={`${id}-title`}
            className="font-display text-sm tracking-[0.16em] text-slate-50 uppercase"
          >
            <DecodeText text={`Subdivisión «${category.name}»`} />
          </h2>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="hud-icon-btn">
            ×
          </button>
        </div>

        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div>
            <label htmlFor={`${id}-name`} className="hud-label">
              Nombre
            </label>
            <input
              id={`${id}-name`}
              value={draft.name}
              maxLength={NAME_MAX}
              aria-invalid={fields.name !== undefined}
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
            <label htmlFor={`${id}-color`} className="hud-label">
              Color
            </label>
            <input
              id={`${id}-color`}
              type="color"
              value={draft.color.toLowerCase()}
              onChange={(event) => {
                set('color', event.target.value.toUpperCase());
              }}
              className="h-9 w-14 cursor-pointer rounded border border-sky-400/30 bg-transparent"
            />
            {fields.color?.map((message) => (
              <p key={message} className="mt-1 text-xs text-rose-300">
                {message}
              </p>
            ))}
          </div>
        </div>

        <div>
          <label htmlFor={`${id}-description`} className="hud-label">
            Qué entra en ella <span className="font-normal text-slate-500">(lo lee la IA)</span>
          </label>
          <textarea
            id={`${id}-description`}
            value={draft.description}
            maxLength={DESCRIPTION_MAX}
            rows={3}
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

        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-slate-200">
            Prendida{' '}
            <span className="text-xs text-slate-500">
              {category.is_other
                ? '(«Otros» no se apaga: es a donde va lo que no encaja)'
                : '(la IA la usa al clasificar y se puede buscar)'}
            </span>
          </span>
          <HudSwitch
            checked={draft.is_active}
            disabled={category.is_other}
            onChange={(checked) => {
              set('is_active', checked);
            }}
            label="Prendida"
          />
        </div>

        {topic ? (
          <div className="space-y-4 border-t border-sky-400/10 pt-5">
            <p className="text-xs leading-snug text-slate-400">
              Palabras del tema general. Solo, trae las notas con cualquiera de ellas; junto con la
              FGR, solo las que traen la FGR <span className="text-slate-200">y</span> una de ellas.
            </p>
            <KeywordChips
              label="Palabras clave"
              hint="Enter o coma para agregar; puedes pegar una lista."
              tone="keyword"
              terms={draft.keywords}
              errors={termFields.keywords}
              onChange={(terms) => {
                set('keywords', terms);
              }}
            />
            <KeywordChips
              label="Exclusiones"
              hint="Una nota se descarta si menciona alguna."
              tone="exclude"
              terms={draft.exclude_terms}
              errors={termFields.exclude_terms}
              onChange={(terms) => {
                set('exclude_terms', terms);
              }}
            />
          </div>
        ) : (
          !category.is_other && (
            <p className="border-t border-sky-400/10 pt-5 text-xs text-slate-400">
              Todavía no tiene tema general para buscarla. Se crea con{' '}
              <code className="font-mono text-slate-300">wsl make seed</code>.
            </p>
          )
        )}

        {general && (
          <p
            role="alert"
            className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200"
          >
            {general}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-sky-400/10 pt-5">
          <HudButton type="submit" variant="solid" disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar cambios'}
          </HudButton>
          <HudButton variant="ghost" onClick={onClose}>
            Cerrar
          </HudButton>
          {saved && (
            <span role="status" className="text-xs text-emerald-300">
              Guardado.
            </span>
          )}
        </div>
      </form>
    </HudPanel>
  );
}
