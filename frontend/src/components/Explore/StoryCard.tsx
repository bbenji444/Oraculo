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
import { CategoryTag } from './CategoryTag';
import { formatDay, isCoarse, PRECISION_LABEL, providersLabel } from './format';
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
  /**
   * Compacta (expediente del Centro de mando): un solo renglón de datos con
   * la categoría al final y sin la fuente; caben muchas más (28/10/2026).
   */
  dense?: boolean;
}

function ArticleRow({
  article,
  colors,
  isSelected,
  selectedRef,
  onSelect,
  nested = false,
  dense = false,
}: ArticleRowProps) {
  const concept = article.concepts.find((c) => c.is_relevant);
  const location = article.primary_location;
  // El punto va del color de la categoría; sin categoría, del concepto.
  const dot =
    article.category?.color ??
    (concept ? (colors.get(concept.concept_id) ?? DEFAULT_CONCEPT_COLOR) : NO_CONCEPT_COLOR);
  const place = (
    <span className={location && isCoarse(location.precision) ? 'text-sky-200/70' : ''}>
      {location?.place ?? PRECISION_LABEL.unknown}
    </span>
  );
  return (
    <button
      ref={isSelected ? selectedRef : undefined}
      type="button"
      aria-current={isSelected}
      onClick={() => {
        onSelect(article.article_id);
      }}
      className={`flex w-full gap-2.5 rounded-xl border text-left transition-all duration-300 focus-visible:outline-2 focus-visible:outline-sky-400 ${
        dense ? 'px-2.5 py-1' : nested ? 'px-2.5 py-1.5' : 'px-3 py-2'
      } ${
        isSelected
          ? 'border-sky-400/50 bg-sky-400/[0.12] shadow-[0_0_18px_rgb(0_210_255/0.15)]'
          : 'border-transparent bg-white/[0.03] hover:translate-x-0.5 hover:border-sky-400/25 hover:bg-sky-400/[0.06]'
      }`}
    >
      <span
        aria-hidden="true"
        className={`mt-1.5 shrink-0 rounded-full ${nested ? 'size-1.5' : 'size-2'}`}
        style={{ backgroundColor: dot, boxShadow: `0 0 6px ${dot}` }}
      />
      <span className="min-w-0 flex-1">
        <span
          title={dense ? article.title : undefined}
          className={`leading-snug text-slate-100 ${nested ? 'text-[12px]' : 'text-[13px]'} ${
            // Compacta: una línea; el título completo al elegirla o al pasar el mouse.
            dense && !isSelected ? 'block truncate' : 'line-clamp-2'
          }`}
        >
          {article.title}
        </span>
        {dense ? (
          <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[10.5px] text-slate-400">
            <span className="min-w-0 shrink truncate">
              {article.source_name ?? article.source_domain ?? '—'}
              {article.published_at && ` · ${formatDay(article.published_at)}`}
              {' · '}
              {place}
            </span>
            <span className="ml-auto max-w-[45%] shrink-0">
              <CategoryTag article={article} />
            </span>
          </span>
        ) : (
          <span className="mt-0.5 block truncate text-[11px] text-slate-400">
            {article.source_name ?? article.source_domain ?? '—'}
            {article.published_at && ` · ${formatDay(article.published_at)}`}
            {' · '}
            {place}
          </span>
        )}
        {!dense && (Boolean(article.category) || article.providers.length > 0) && (
          // El delito según la IA (F12.4) y de qué fuente vino la nota (F12.2).
          <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[10px] text-slate-500">
            <CategoryTag article={article} />
            {article.providers.length > 0 && (
              <span className="truncate">vía {providersLabel(article.providers)}</span>
            )}
          </span>
        )}
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
  /** Versión compacta (expediente del Centro de mando). */
  dense?: boolean;
}

export function StoryCard({
  group,
  colors,
  selectedId,
  selectedRef,
  onSelect,
  dense = false,
}: StoryCardProps) {
  const [open, setOpen] = useState(false);
  const { lead, others } = group;
  const selectedInside = others.some((a) => a.article_id === selectedId);
  const expanded = open || selectedInside;
  const listId = `historia-${String(lead.article_id)}`;
  const row = (
    <ArticleRow
      article={lead}
      colors={colors}
      isSelected={lead.article_id === selectedId}
      selectedRef={selectedRef}
      onSelect={onSelect}
      dense={dense}
    />
  );
  const toggle = () => {
    setOpen(!expanded);
  };
  if (dense) {
    // Compacta: «+N» a la derecha del renglón, no en uno aparte.
    return (
      <div>
        <div className="flex items-start gap-1">
          <div className="min-w-0 flex-1">{row}</div>
          {others.length > 0 && (
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={listId}
              onClick={toggle}
              title={moreOutletsLabel(others.length)}
              aria-label={moreOutletsLabel(others.length)}
              className="mt-2 shrink-0 rounded-full border border-sky-400/30 bg-sky-400/10 px-1.5 text-[10px] text-sky-200 transition-colors hover:border-sky-400/60 focus-visible:outline-2 focus-visible:outline-sky-400"
            >
              +{others.length}
            </button>
          )}
        </div>
        {expanded && others.length > 0 && (
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
      </div>
    );
  }
  return (
    <div>
      {row}
      {others.length > 0 && (
        <>
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={listId}
            onClick={toggle}
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
