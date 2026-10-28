/**
 * Botón «Filtro» del expediente y su ventana al centro de la pantalla (Benji,
 * 28/10/2026: «que solo diga filtro y de ahí seleccionar los parámetros»;
 * «que la ventana pop aparezca en el centro»).
 *
 * Adentro, ordenado:
 * - **Categorías**: cuadros de color en cuadrícula (`CategoryFilter`), uno o
 *   varios;
 * - **Estado**: lista desplegable;
 * - **Ubicación**: todas, dentro de la región, fuera o sin lugar;
 * - **No relevantes**: incluirlas o no.
 *
 * El botón dice cuántos filtros hay puestos («Filtro · 2»). Se cierra con
 * «Listo», con Esc o con un clic en el fondo oscuro.
 *
 * No hace: no filtra por su cuenta; escribe en los stores, que comparten la
 * cronología, la lista y el globo.
 */
import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import type { Article } from '../../services/searches';
import { type ListFilter, useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import { statesIn } from '../Explore/timelineData';
import { GLASS } from '../Explore/ui';
import { HudSegmented } from '../ui/HudSegmented';
import { HudSelect } from '../ui/HudSelect';
import { HudSwitch } from '../ui/HudSwitch';
import { CategoryFilter } from './CategoryFilter';
import { activeFilters } from './mission';

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
  const stateId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
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

  // Esc la cierra y, al abrir, el foco entra a la ventana.
  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const clearAll = () => {
    clearTimeline();
    setListFilter('all');
    setShowIrrelevant(false);
  };

  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          setOpen(true);
        }}
        className={`hud-btn hud-btn--sm flex items-center gap-1.5 px-3 ${count > 0 ? 'border-sky-300/60 text-sky-100' : ''}`}
      >
        <svg aria-hidden="true" viewBox="0 0 16 16" className="size-3.5 fill-current">
          <path d="M1.5 2.5h13l-5 6v4.5l-3 1.5v-6z" />
        </svg>
        Filtro
        {count > 0 && <span className="mando-filter-count">{count}</span>}
      </button>

      {open &&
        createPortal(
          // El fondo oscuro cierra la ventana; la ventana va al centro.
          <div
            className="mando-modal-backdrop fixed inset-0 z-[60] flex items-center justify-center p-4"
            onPointerDown={(event) => {
              if (event.target === event.currentTarget) setOpen(false);
            }}
          >
            <div
              ref={panelRef}
              id={panelId}
              role="dialog"
              aria-modal="true"
              aria-label="Filtrar el expediente"
              tabIndex={-1}
              // Opaca: encima del globo y del listado, el vidrio no se leía.
              className={`${GLASS} mando-modal w-[36rem] max-w-full space-y-4 bg-[#06121a]/[0.98] p-5 outline-none`}
            >
              <div className="flex items-center justify-between">
                <p className="mando-kicker">Filtrar el expediente</p>
                <div className="flex items-center gap-3">
                  {count > 0 && (
                    <button
                      type="button"
                      onClick={clearAll}
                      className="text-[11px] text-sky-300 hover:text-sky-100 focus-visible:outline-2 focus-visible:outline-sky-400"
                    >
                      Quitar filtros
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                    }}
                    aria-label="Cerrar el filtro"
                    className="hud-icon-btn size-7 text-sm"
                  >
                    ×
                  </button>
                </div>
              </div>

              <section aria-label="Categorías" className="space-y-2">
                <p className="hud-label mb-0">Categorías</p>
                <CategoryFilter articles={articles} />
              </section>

              <div className="space-y-4">
                <section className="space-y-2">
                  <label htmlFor={stateId} className="hud-label mb-0 block">
                    Estado
                  </label>
                  <HudSelect
                    id={stateId}
                    size="sm"
                    value={stateCode ?? ''}
                    options={[
                      { value: '', label: 'Todos los estados' },
                      ...states.map((s) => ({
                        value: s.code,
                        label: `${s.name} (${String(s.count)})`,
                      })),
                    ]}
                    onChange={(next) => {
                      setState(next || null);
                    }}
                  />
                </section>
                <section aria-label="Ubicación" className="space-y-2">
                  <p className="hud-label mb-0">Ubicación</p>
                  <HudSegmented
                    options={LOCATIONS}
                    value={listFilter}
                    onChange={setListFilter}
                    label="Filtrar por ubicación"
                  />
                </section>
              </div>

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
                className="hud-btn hud-btn--solid w-full py-2.5 text-[11px]"
              >
                Listo
              </button>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
