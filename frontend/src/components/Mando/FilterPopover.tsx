/**
 * Botón «Filtro» del expediente y su ventana (Benji, 28/10/2026: «que solo
 * diga filtro y de ahí seleccionar los parámetros»). Los botones de color de
 * las categorías ocupaban mucho del listado; ahora todo va en una ventana que
 * se abre encima.
 *
 * Adentro:
 * - **Categorías**: los botones de color (`CategoryFilter`), uno o varios;
 * - **Estado**: uno, o todos;
 * - **Ubicación**: todas, dentro de la región, fuera o sin ubicación;
 * - **No relevantes**: incluirlas o no.
 *
 * El botón dice cuántos filtros hay puestos («Filtro · 2»). Se cierra con
 * «Listo», con Esc o con un clic afuera.
 *
 * No hace: no filtra por su cuenta; escribe en los stores, que comparten la
 * cronología, la lista y el globo.
 */
import { useEffect, useId, useRef, useState } from 'react';

import type { Article } from '../../services/searches';
import { type ListFilter, useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import { statesIn } from '../Explore/timelineData';
import { HudSegmented } from '../ui/HudSegmented';
import { HudSwitch } from '../ui/HudSwitch';
import { CategoryFilter } from './CategoryFilter';
import { activeFilters } from './mission';
import { GLASS } from '../Explore/ui';

const LOCATIONS = [
  { value: 'all', label: 'Todas' },
  { value: 'true', label: 'Dentro' },
  { value: 'false', label: 'Fuera' },
  { value: 'none', label: 'Sin lugar' },
] as const satisfies readonly { value: ListFilter; label: string }[];

interface FilterPopoverProps {
  /** Las notas de la consulta, antes de estos filtros (para contar). */
  articles: readonly Article[];
}

export function FilterPopover({ articles }: FilterPopoverProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const categoryIds = useTimelineStore((s) => s.categoryIds);
  const stateCode = useTimelineStore((s) => s.stateCode);
  const setState = useTimelineStore((s) => s.setState);
  const clearTimeline = useTimelineStore((s) => s.clear);
  const listFilter = useExplorerStore((s) => s.listFilter);
  const setListFilter = useExplorerStore((s) => s.setListFilter);
  const showIrrelevant = useExplorerStore((s) => s.showIrrelevant);
  const setShowIrrelevant = useExplorerStore((s) => s.setShowIrrelevant);
  const count = activeFilters(categoryIds, stateCode, listFilter, showIrrelevant);
  const states = statesIn(articles);

  // Esc o un clic afuera la cierran.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const onDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('pointerdown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('pointerdown', onDown);
    };
  }, [open]);

  const clearAll = () => {
    clearTimeline();
    setListFilter('all');
    setShowIrrelevant(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          setOpen(!open);
        }}
        className={`hud-btn hud-btn--sm flex items-center gap-1.5 px-3 ${count > 0 ? 'border-sky-300/60 text-sky-100' : ''}`}
      >
        <svg aria-hidden="true" viewBox="0 0 16 16" className="size-3.5 fill-current">
          <path d="M1.5 2.5h13l-5 6v4.5l-3 1.5v-6z" />
        </svg>
        Filtro
        {count > 0 && <span className="mando-filter-count">{count}</span>}
      </button>

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label="Filtrar el expediente"
          // Opaca: encima del listado, el vidrio translúcido dejaba ver las notas de atrás.
          className={`${GLASS} mando-popover bg-[#06121a]/[0.98] absolute right-0 top-[calc(100%+8px)] z-40 w-[26rem] max-w-[calc(100vw-2rem)] space-y-3.5 p-4`}
        >
          <div className="flex items-center justify-between">
            <p className="mando-kicker">Filtrar el expediente</p>
            {count > 0 && (
              <button
                type="button"
                onClick={clearAll}
                className="text-[11px] text-sky-300 hover:text-sky-100 focus-visible:outline-2 focus-visible:outline-sky-400"
              >
                Quitar filtros
              </button>
            )}
          </div>

          <section aria-label="Categorías" className="space-y-1.5">
            <p className="hud-label mb-0">Categorías</p>
            <CategoryFilter articles={articles} />
          </section>

          {states.length > 0 && (
            <section aria-label="Estado" className="space-y-1.5">
              <p className="hud-label mb-0">Estado</p>
              <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto pr-1">
                <button
                  type="button"
                  aria-pressed={stateCode === null}
                  onClick={() => {
                    setState(null);
                  }}
                  className="mando-cat"
                >
                  Todos
                </button>
                {states.map((state) => (
                  <button
                    key={state.code}
                    type="button"
                    aria-pressed={stateCode === state.code}
                    onClick={() => {
                      setState(stateCode === state.code ? null : state.code);
                    }}
                    className="mando-cat"
                  >
                    <span className="truncate">{state.name}</span>
                    <span className="mando-cat-count">{state.count}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <section aria-label="Ubicación" className="space-y-1.5">
            <p className="hud-label mb-0">Ubicación</p>
            <HudSegmented
              options={LOCATIONS}
              value={listFilter}
              onChange={setListFilter}
              label="Filtrar por ubicación"
            />
          </section>

          <div className="flex items-center justify-between gap-3 border-t border-sky-400/10 pt-3">
            <span className="text-[11.5px] text-slate-300">Incluir las no relevantes</span>
            <HudSwitch
              checked={showIrrelevant}
              onChange={setShowIrrelevant}
              label="Incluir las no relevantes"
            />
          </div>

          <button
            type="button"
            onClick={() => {
              setOpen(false);
            }}
            className="hud-btn hud-btn--solid w-full py-2 text-[11px]"
          >
            Listo
          </button>
        </div>
      )}
    </div>
  );
}
