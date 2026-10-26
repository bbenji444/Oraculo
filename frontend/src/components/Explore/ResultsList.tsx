/**
 * Lista de noticias de la búsqueda, sincronizada con el globo: elegir una nota
 * aquí o en el mapa es la misma acción (store). Pestañas Dentro de la región,
 * Fuera y Sin ubicación (§9 paso 7: las de fuera no se borran, se muestran
 * aparte). Recibe las notas ya filtradas por relevancia (las mismas que el
 * globo); su interruptor "No relevantes" cambia el store y afecta a los dos.
 * El encabezado dice cuántas se ven de cuántas trajo la búsqueda ("24 de 43").
 * Las notas del mismo hecho en varios medios van en una sola tarjeta con
 * «▸ +N medios» (ADR-0026); debajo de las pestañas se dice en cuántas.
 */
import { useEffect, useRef } from 'react';

import type { Article } from '../../services/searches';
import { type ListFilter, useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import { newsCount } from './format';
import { groupByStory } from './stories';
import { StoryCard } from './StoryCard';
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
  /** Notas visibles (ver `visibleArticles`). */
  articles: readonly Article[];
  /** Todas las notas de la búsqueda, relevantes o no. */
  total: number;
  colors: ReadonlyMap<number, string>;
}

export function ResultsList({ articles, total, colors }: ResultsListProps) {
  const filter = useExplorerStore((s) => s.listFilter);
  const setFilter = useExplorerStore((s) => s.setListFilter);
  const articleId = useExplorerStore((s) => s.articleId);
  const selectArticle = useExplorerStore((s) => s.selectArticle);
  const showIrrelevant = useExplorerStore((s) => s.showIrrelevant);
  const setShowIrrelevant = useExplorerStore((s) => s.setShowIrrelevant);
  const selectedRef = useRef<HTMLButtonElement>(null);
  const shown = articles.filter((a) => matches(a, filter));
  // Mismo hecho en varios medios = una tarjeta con «▸ +N medios» (ADR-0026).
  const groups = groupByStory(shown);
  const count = newsCount(articles.length, total);

  useEffect(() => {
    // La nota elegida en el globo se trae a la vista en la lista.
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [articleId]);

  return (
    <section aria-label="Noticias" className={`${GLASS} flex min-h-0 flex-col p-4`}>
      <div className="flex items-center justify-between">
        <h2 className={PANEL_TITLE} title={count.hint}>
          {count.label}
        </h2>
        <button
          type="button"
          onClick={() => {
            useTimelineStore.getState().setListOpen(false);
          }}
          title="Volver a la cronología"
          className="ml-auto mr-3 rounded-full border border-sky-400/20 px-2 py-0.5 text-[11px] text-sky-200 hover:border-sky-400/50 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          ◷ Cronología
        </button>
        <label className="flex items-center gap-1.5 text-[11px] text-slate-400">
          <input
            type="checkbox"
            checked={showIrrelevant}
            onChange={(event) => {
              setShowIrrelevant(event.target.checked);
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
            {tab.label} · {articles.filter((a) => matches(a, tab.id)).length}
          </button>
        ))}
      </div>
      {groups.length < shown.length && (
        <p className="mt-2 text-[11px] text-slate-500">
          {shown.length} notas en {groups.length} tarjetas: las del mismo hecho van juntas.
        </p>
      )}
      <ul className="mt-3 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {shown.length === 0 && <li className="text-xs text-slate-500">Nada en esta pestaña.</li>}
        {groups.map((group) => (
          <li key={group.lead.article_id}>
            <StoryCard
              group={group}
              colors={colors}
              selectedId={articleId}
              selectedRef={selectedRef}
              onSelect={selectArticle}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
