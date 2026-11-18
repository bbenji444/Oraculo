/**
 * Lista de noticias de la búsqueda, sincronizada con el globo: elegir una nota
 * aquí o en el mapa es la misma acción (store). Pestañas Dentro de la región,
 * Fuera y Sin ubicación (§9 paso 7: las de fuera no se borran, se muestran
 * aparte). Recibe las notas ya filtradas por relevancia (las mismas que el
 * globo); su interruptor "No relevantes" cambia el store y afecta a los dos.
 * El encabezado dice cuántas se ven de cuántas trajo la búsqueda ("24 de 43").
 * Las notas del mismo hecho en varios medios van en una sola tarjeta con
 * «▸ +N medios» (ADR-0026); debajo de las pestañas se dice en cuántas.
 * Si hay notas de más de una categoría, las tarjetas van en secciones
 * plegables por categoría con su conteo (ADR-0109, D5).
 */
import { type CSSProperties, useEffect, useRef, useState } from 'react';

import type { Article } from '../../services/searches';
import { type ListFilter, useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import { type CategorySection, containsArticle, sectionsByCategory } from './categorySections';
import { matchesListFilter, newsCount } from './format';
import { type StoryGroup, groupByStory } from './stories';
import { StoryCard } from './StoryCard';
import { GLASS, PANEL_TITLE } from './ui';

const TABS: { id: ListFilter; label: string }[] = [
  { id: 'all', label: 'Todas' },
  { id: 'true', label: 'Dentro de zona' },
  { id: 'false', label: 'Fuera de zona' },
  { id: 'none', label: 'Sin ubicación' },
];

function matches(article: Article, filter: ListFilter): boolean {
  return matchesListFilter(article, filter);
}

interface ResultsListProps {
  /** Notas visibles (ver `visibleArticles`). */
  articles: readonly Article[];
  /** Todas las notas de la búsqueda, relevantes o no. */
  total: number;
  colors: ReadonlyMap<number, string>;
  /**
   * `column`: el panel del diseño de columna. `dossier`: dentro del expediente
   * del Centro de mando, que ya tiene las pestañas «Cronología | Noticias»:
   * sin marco ni título propios, con tarjetas compactas para que quepan muchas
   * más noticias (Benji, 28/10/2026).
   */
  variant?: 'column' | 'dossier';
}

export function ResultsList({ articles, total, colors, variant = 'column' }: ResultsListProps) {
  const dossier = variant === 'dossier';
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
  const sections = sectionsByCategory(groups);
  // Con una sola categoría la sección no dice nada nuevo: cada tarjeta ya
  // lleva su etiqueta.
  const sectioned = sections.length > 1;
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());
  const count = newsCount(articles.length, total);
  const toggleSection = (key: string) => {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  };
  const renderCard = (group: StoryGroup) => (
    <li key={group.lead.article_id}>
      <StoryCard
        group={group}
        colors={colors}
        selectedId={articleId}
        selectedRef={selectedRef}
        onSelect={selectArticle}
        dense={dossier}
      />
    </li>
  );

  useEffect(() => {
    // La nota elegida en el globo se trae a la vista en la lista.
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [articleId]);

  return (
    <section
      aria-label="Noticias"
      className={
        dossier
          ? 'flex min-h-0 flex-1 flex-col px-3 pb-2 pt-2'
          : `${GLASS} flex min-h-0 flex-col p-4`
      }
    >
      {/* En el expediente, el conteo y la ubicación van en «Filtro». */}
      {!dossier && (
        <>
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
          <div
            className="hud-seg mt-3"
            role="tablist"
            aria-label="Filtrar por región"
            style={
              {
                '--seg-i': Math.max(
                  0,
                  TABS.findIndex((tab) => tab.id === filter),
                ),
                '--seg-n': TABS.length,
              } as CSSProperties
            }
          >
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={filter === tab.id}
                onClick={() => {
                  setFilter(tab.id);
                }}
                className="px-1 text-[9px] focus-visible:outline-2 focus-visible:outline-sky-400"
              >
                {tab.label} · {articles.filter((a) => matches(a, tab.id)).length}
              </button>
            ))}
          </div>
        </>
      )}
      {!dossier && groups.length < shown.length && (
        <p className="mt-2 text-[11px] text-slate-500">
          {shown.length} notas en {groups.length} tarjetas: las del mismo hecho van juntas.
        </p>
      )}
      <ul
        className={`min-h-0 flex-1 overflow-y-auto pr-1 ${dossier ? '' : 'mt-3'} ${
          sectioned ? 'space-y-2' : dossier ? 'space-y-1' : 'space-y-1.5'
        }`}
      >
        {shown.length === 0 && <li className="text-xs text-slate-500">Nada en esta pestaña.</li>}
        {sectioned
          ? sections.map((section) => {
              // La nota elegida en el globo abre su sección para que se vea.
              const open = !collapsed.has(section.key) || containsArticle(section, articleId);
              return (
                <li key={section.key}>
                  <CategoryHeader
                    section={section}
                    open={open}
                    dense={dossier}
                    onToggle={() => {
                      toggleSection(section.key);
                    }}
                  />
                  {open && (
                    <ul className={`mt-1 ${dossier ? 'space-y-1' : 'space-y-1.5'}`}>
                      {section.groups.map(renderCard)}
                    </ul>
                  )}
                </li>
              );
            })
          : groups.map(renderCard)}
      </ul>
    </section>
  );
}

interface CategoryHeaderProps {
  section: CategorySection;
  open: boolean;
  /** Más chica en el expediente del Centro de mando. */
  dense: boolean;
  onToggle: () => void;
}

/** Renglón de una categoría: color, nombre y cuántas notas trae; pliega la sección. */
function CategoryHeader({ section, open, dense, onToggle }: CategoryHeaderProps) {
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-label={`${section.name}: ${String(section.count)} ${section.count === 1 ? 'nota' : 'notas'}`}
      onClick={onToggle}
      className={`flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left uppercase tracking-wider text-slate-300 hover:bg-sky-400/5 focus-visible:outline-2 focus-visible:outline-sky-400 ${
        dense ? 'text-[10px]' : 'text-[11px]'
      }`}
    >
      <span aria-hidden="true" className="w-2 text-slate-500">
        {open ? '▾' : '▸'}
      </span>
      <span
        aria-hidden="true"
        className="size-2 shrink-0 rounded-full"
        style={{ backgroundColor: section.color }}
      />
      <span className="min-w-0 flex-1 truncate">{section.name}</span>
      <span className="tabular-nums text-slate-400">{section.count}</span>
    </button>
  );
}
