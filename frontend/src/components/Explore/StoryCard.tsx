/**
 * Una tarjeta de la lista de noticias: la nota principal de una historia y,
 * si el mismo hecho lo publicaron otros medios, el chevron «▸ +N medios» que
 * despliega las demás (ADR-0026). Una nota sola se ve igual que antes.
 *
 * Elegir cualquier nota (la principal o una desplegada) es la misma acción que
 * elegirla en el globo (store). Si la elegida está dentro de la historia, la
 * historia se abre sola para que se vea.
 *
 * No hace: no agrupa (eso es `groupByStory`) ni pide datos.
 */
import { type Ref, useState } from 'react';

import type { Article } from '../../services/searches';
import { formatDay, isCoarse, PRECISION_LABEL } from './format';
import { moreOutletsLabel, type StoryGroup } from './stories';

/** Color del punto de una nota sin concepto relevante (gris de la paleta). */
const NO_CONCEPT_COLOR = '#64748B';
/** Color por defecto de un concepto sin color asignado (cian de la paleta). */
const DEFAULT_CONCEPT_COLOR = '#38BDF8';

interface ArticleRowProps {
  article: Article;
  colors: ReadonlyMap<number, string>;
  isSelected: boolean;
  selectedRef: Ref<HTMLButtonElement>;
  onSelect: (articleId: number) => void;
  /** Fila desplegada dentro de una historia: más compacta y con sangría. */
  nested?: boolean;
}

function ArticleRow({
  article,
  colors,
  isSelected,
  selectedRef,
  onSelect,
  nested = false,
}: ArticleRowProps) {
  const concept = article.concepts.find((c) => c.is_relevant);
  const location = article.primary_location;
  return (
    <button
      ref={isSelected ? selectedRef : undefined}
      type="button"
      aria-current={isSelected}
      onClick={() => {
        onSelect(article.article_id);
      }}
      className={`flex w-full gap-2.5 rounded-xl border text-left transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
        nested ? 'px-2.5 py-1.5' : 'px-3 py-2'
      } ${
        isSelected
          ? 'border-sky-400/50 bg-sky-500/15'
          : 'border-transparent bg-white/[0.03] hover:bg-white/[0.07]'
      }`}
    >
      <span
        aria-hidden="true"
        className={`mt-1.5 shrink-0 rounded-full ${nested ? 'size-1.5' : 'size-2'}`}
        style={{
          backgroundColor: concept
            ? (colors.get(concept.concept_id) ?? DEFAULT_CONCEPT_COLOR)
            : NO_CONCEPT_COLOR,
        }}
      />
      <span className="min-w-0">
        <span
          className={`line-clamp-2 leading-snug text-slate-100 ${nested ? 'text-[12px]' : 'text-[13px]'}`}
        >
          {article.title}
        </span>
        <span className="mt-0.5 block truncate text-[11px] text-slate-400">
          {article.source_name ?? article.source_domain ?? '—'}
          {article.published_at && ` · ${formatDay(article.published_at)}`}
          {' · '}
          <span className={location && isCoarse(location.precision) ? 'text-amber-200/80' : ''}>
            {location?.place ?? PRECISION_LABEL.unknown}
          </span>
        </span>
      </span>
    </button>
  );
}

interface StoryCardProps {
  group: StoryGroup;
  colors: ReadonlyMap<number, string>;
  /** Nota elegida en el store, o `null`. */
  selectedId: number | null;
  selectedRef: Ref<HTMLButtonElement>;
  onSelect: (articleId: number) => void;
}

export function StoryCard({ group, colors, selectedId, selectedRef, onSelect }: StoryCardProps) {
  const [open, setOpen] = useState(false);
  const { lead, others } = group;
  const selectedInside = others.some((a) => a.article_id === selectedId);
  const expanded = open || selectedInside;
  const listId = `historia-${String(lead.article_id)}`;
  return (
    <div>
      <ArticleRow
        article={lead}
        colors={colors}
        isSelected={lead.article_id === selectedId}
        selectedRef={selectedRef}
        onSelect={onSelect}
      />
      {others.length > 0 && (
        <>
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={listId}
            onClick={() => {
              setOpen(!expanded);
            }}
            className="mt-0.5 ml-7 rounded-md px-1.5 py-0.5 text-[11px] text-sky-300/90 transition-colors hover:bg-white/5 hover:text-sky-200 focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            <span aria-hidden="true">{expanded ? '▼' : '▸'}</span> {moreOutletsLabel(others.length)}
          </button>
          {expanded && (
            <ul
              id={listId}
              aria-label="Otros medios con el mismo hecho"
              className="mt-1 ml-5 space-y-1 border-l border-white/10 pl-2"
            >
              {others.map((article) => (
                <li key={article.article_id}>
                  <ArticleRow
                    article={article}
                    colors={colors}
                    isSelected={article.article_id === selectedId}
                    selectedRef={selectedRef}
                    onSelect={onSelect}
                    nested
                  />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
