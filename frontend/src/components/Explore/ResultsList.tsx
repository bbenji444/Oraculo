/**
 * Lista de noticias de la búsqueda, sincronizada con el globo: elegir una nota
 * aquí o en el mapa es la misma acción (store). Pestañas Dentro de la región,
 * Fuera y Sin ubicación (§9 paso 7: las de fuera no se borran, se muestran
 * aparte). Por defecto solo las relevantes; un interruptor muestra todas.
 */
import { useEffect, useRef, useState } from 'react';

import type { Article } from '../../services/searches';
import { type ListFilter, useExplorerStore } from '../../store/explorer';
import { formatDay, isCoarse, PRECISION_LABEL } from './format';
import { GLASS, PANEL_TITLE } from './ui';

const TABS: { id: ListFilter; label: string }[] = [
  { id: 'all', label: 'Todas' },
  { id: 'true', label: 'Dentro' },
  { id: 'false', label: 'Fuera' },
  { id: 'none', label: 'Sin ubicación' },
];

function matches(article: Article, filter: ListFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'none') return article.in_region === null;
  return article.in_region === (filter === 'true');
}

interface ResultsListProps {
  articles: readonly Article[];
  colors: ReadonlyMap<number, string>;
}

export function ResultsList({ articles, colors }: ResultsListProps) {
  const filter = useExplorerStore((s) => s.listFilter);
  const setFilter = useExplorerStore((s) => s.setListFilter);
  const articleId = useExplorerStore((s) => s.articleId);
  const selectArticle = useExplorerStore((s) => s.selectArticle);
  const [showAll, setShowAll] = useState(false);
  const selectedRef = useRef<HTMLButtonElement>(null);
  const visible = articles.filter((a) => showAll || a.concepts.some((c) => c.is_relevant));
  const shown = visible.filter((a) => matches(a, filter));

  useEffect(() => {
    // La nota elegida en el globo se trae a la vista en la lista.
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [articleId]);

  return (
    <section aria-label="Noticias" className={`${GLASS} flex min-h-0 flex-col p-4`}>
      <div className="flex items-center justify-between">
        <h2 className={PANEL_TITLE}>Noticias ({visible.length})</h2>
        <label className="flex items-center gap-1.5 text-[11px] text-slate-400">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(event) => {
              setShowAll(event.target.checked);
            }}
            className="accent-sky-400"
          />
          No relevantes
        </label>
      </div>
      <div className="mt-3 grid grid-cols-4 gap-1" role="tablist" aria-label="Filtrar por región">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={filter === tab.id}
            onClick={() => {
              setFilter(tab.id);
            }}
            className={`rounded-lg px-1 py-1 text-[11px] transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
              filter === tab.id
                ? 'bg-sky-500/25 text-sky-100'
                : 'bg-white/5 text-slate-400 hover:bg-white/10'
            }`}
          >
            {tab.label} · {visible.filter((a) => matches(a, tab.id)).length}
          </button>
        ))}
      </div>
      <ul className="mt-3 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {shown.length === 0 && <li className="text-xs text-slate-500">Nada en esta pestaña.</li>}
        {shown.map((article) => {
          const concept = article.concepts.find((c) => c.is_relevant);
          const location = article.primary_location;
          const isSelected = article.article_id === articleId;
          return (
            <li key={article.article_id}>
              <button
                ref={isSelected ? selectedRef : undefined}
                type="button"
                aria-current={isSelected}
                onClick={() => {
                  selectArticle(article.article_id);
                }}
                className={`flex w-full gap-2.5 rounded-xl border px-3 py-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
                  isSelected
                    ? 'border-sky-400/50 bg-sky-500/15'
                    : 'border-transparent bg-white/[0.03] hover:bg-white/[0.07]'
                }`}
              >
                <span
                  aria-hidden="true"
                  className="mt-1.5 size-2 shrink-0 rounded-full"
                  style={{
                    backgroundColor: concept
                      ? (colors.get(concept.concept_id) ?? '#38BDF8')
                      : '#64748B',
                  }}
                />
                <span className="min-w-0">
                  <span className="line-clamp-2 text-[13px] leading-snug text-slate-100">
                    {article.title}
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-slate-500">
                    {article.source_name ?? article.source_domain ?? '—'}
                    {article.published_at && ` · ${formatDay(article.published_at)}`}
                    {' · '}
                    <span
                      className={
                        location && isCoarse(location.precision) ? 'text-amber-200/80' : ''
                      }
                    >
                      {location?.place ?? PRECISION_LABEL.unknown}
                    </span>
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
