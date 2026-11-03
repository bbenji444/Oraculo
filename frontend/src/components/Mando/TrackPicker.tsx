/**
 * Ventana «¿Qué rastrear?» del Centro de mando, al centro de la pantalla
 * (Benji, 02/11/2026; ADR-0038). Se abre al tocar la parte 01 de la frase.
 *
 * Dos bloques:
 * - **Fiscalía General de la República**: la FGR completa («Todas») o con
 *   una o varias subdivisiones. Con una subdivisión, la búsqueda trae solo
 *   notas con las dos cosas: la FGR y una palabra de la subdivisión
 *   («FGR · Homicidio»).
 * - **Temas generales**: cada subdivisión por su cuenta, sin la FGR
 *   («solo homicidios en general»).
 *
 * Se puede elegir de los dos bloques a la vez. Se cierra con «Listo», con Esc
 * o con un clic en el fondo oscuro.
 *
 * Todo sale de los conceptos: el tema general de una subdivisión trae su id
 * (`category_id`), su nombre y su color. El catálogo de subdivisiones solo da
 * el orden; si no se pudo leer, se ordena por nombre.
 *
 * No hace: no busca ni decide reglas; escribe en `useExplorerStore` y el
 * servidor valida (una subdivisión sola, sin la FGR, no se manda).
 */
import { type CSSProperties, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

import { useCategories } from '../../hooks/useCategories';
import { useConcepts } from '../../hooks/useConcepts';
import type { Category } from '../../services/categories';
import type { Concept } from '../../services/concepts';
import { useExplorerStore } from '../../store/explorer';
import { hexToRgb } from '../Explore/categoryColor';
import { GLASS } from '../Explore/ui';

interface TrackPickerProps {
  onClose: () => void;
}

// Palabras clave que se leen al pasar el mouse por un tema: las primeras dan la idea.
const TITLE_KEYWORDS = 4;

/** Un tema general: el concepto de una subdivisión, con el id de ella. */
type Topic = Concept & { category_id: number };

/**
 * Los temas generales en el orden del catálogo (o por nombre, si no se leyó).
 *
 * @param concepts Conceptos activos.
 * @param categories Catálogo de subdivisiones, si ya llegó.
 */
function topicsOf(concepts: readonly Concept[], categories: readonly Category[] = []): Topic[] {
  const order = new Map(categories.map((c, index) => [c.id, index]));
  const rank = (topic: Topic) => order.get(topic.category_id) ?? order.size;
  return concepts
    .filter((c): c is Topic => c.category_id !== null)
    .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, 'es'));
}

/** Un cuadro de color de la cuadrícula. */
function Tile({
  label,
  color,
  pressed,
  dim,
  title,
  onClick,
}: {
  label: string;
  color: string;
  pressed: boolean;
  dim?: boolean;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      title={title}
      data-dim={dim ? '' : undefined}
      className="mando-cat mando-cat--card"
      style={{ '--cat': hexToRgb(color) } as CSSProperties}
    >
      <span aria-hidden="true" className="mando-cat-dot" />
      <span className="mando-cat-name">{label}</span>
    </button>
  );
}

export function TrackPicker({ onClose }: TrackPickerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const concepts = useConcepts().data;
  const categories = useCategories().data;
  const conceptIds = useExplorerStore((s) => s.conceptIds);
  const subdivisionIds = useExplorerStore((s) => s.subdivisionIds);
  const toggleConcept = useExplorerStore((s) => s.toggleConcept);
  const toggleSubdivision = useExplorerStore((s) => s.toggleSubdivision);
  const setSubdivisions = useExplorerStore((s) => s.setSubdivisions);

  // Esc la cierra y, al abrir, el foco entra a la ventana.
  useEffect(() => {
    panelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  const active = (concepts ?? []).filter((c) => c.is_active);
  // Los conceptos que no son tema general: hoy, solo la FGR.
  const bases = active.filter((c) => c.category_id === null);
  const topics = topicsOf(active, categories);
  const baseOn = bases.some((c) => conceptIds.includes(c.id));
  const loading = !concepts;

  // Elegir una subdivisión prende la FGR: sola no se puede buscar.
  const ensureBase = () => {
    const first = bases[0];
    if (!baseOn && first) toggleConcept(first.id);
  };
  const toggleBase = (concept: Concept) => {
    const leaving = conceptIds.includes(concept.id);
    toggleConcept(concept.id);
    // Sin ninguna FGR prendida, sus subdivisiones ya no aplican.
    const othersOn = bases.some((c) => c.id !== concept.id && conceptIds.includes(c.id));
    if (leaving && !othersOn) setSubdivisions([]);
  };

  return createPortal(
    // El fondo oscuro cierra la ventana; la ventana va al centro.
    <div
      className="mando-modal-backdrop fixed inset-0 z-[60] flex items-center justify-center p-4"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        id="mando-editor"
        role="dialog"
        aria-modal="true"
        aria-label="Qué rastrear"
        tabIndex={-1}
        // Opaca, como la del filtro: encima del globo, el vidrio no se leía.
        className={`${GLASS} mando-modal w-[44rem] max-w-full space-y-4 bg-[#06121a]/[0.98] p-5 outline-none`}
      >
        <div className="flex items-center justify-between">
          <p className="mando-kicker">¿Qué rastrear?</p>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="hud-icon-btn size-7 text-sm"
          >
            ×
          </button>
        </div>

        {loading && <p className="text-xs text-slate-500">Cargando conceptos…</p>}

        {!loading && (
          <section aria-label="Fiscalía General de la República" className="space-y-2.5">
            <div className="flex flex-wrap items-center gap-2">
              {bases.map((concept) => (
                <button
                  key={concept.id}
                  type="button"
                  aria-pressed={conceptIds.includes(concept.id)}
                  onClick={() => {
                    toggleBase(concept);
                  }}
                  className="mando-cat px-3 py-1.5 text-[12px]"
                  style={{ '--cat': hexToRgb(concept.color) } as CSSProperties}
                >
                  <span aria-hidden="true" className="mando-cat-dot" />
                  {concept.name}
                </button>
              ))}
            </div>
            {topics.length > 0 && bases.length > 0 && (
              <>
                <p className="text-[11px] leading-snug text-slate-400">
                  Subdivisiones: con una elegida, solo llegan notas que traen la FGR{' '}
                  <span className="text-slate-200">y</span> la subdivisión.
                </p>
                <div
                  role="group"
                  aria-label="Subdivisiones de la FGR"
                  className="grid grid-cols-2 gap-1.5 sm:grid-cols-3"
                >
                  <Tile
                    label="Todas"
                    color="#94A3B8"
                    pressed={baseOn && subdivisionIds.length === 0}
                    onClick={() => {
                      ensureBase();
                      setSubdivisions([]);
                    }}
                  />
                  {topics.map((topic) => {
                    const on = baseOn && subdivisionIds.includes(topic.category_id);
                    return (
                      <Tile
                        key={topic.category_id}
                        label={topic.name}
                        color={topic.color}
                        pressed={on}
                        dim={subdivisionIds.length > 0 && !on}
                        title={`FGR y ${topic.name}`}
                        onClick={() => {
                          if (baseOn) {
                            toggleSubdivision(topic.category_id);
                            return;
                          }
                          // Con la FGR apagada, se prende con solo esta subdivisión.
                          ensureBase();
                          setSubdivisions([topic.category_id]);
                        }}
                      />
                    );
                  })}
                </div>
              </>
            )}
          </section>
        )}

        {!loading && topics.length > 0 && (
          <section
            aria-label="Temas generales"
            className="space-y-2.5 border-t border-sky-400/10 pt-4"
          >
            <div>
              <p className="hud-label mb-0">Temas generales</p>
              <p className="text-[11px] leading-snug text-slate-400">
                Cada tema por su cuenta, sin la FGR: «Homicidio» trae los homicidios en general.
              </p>
            </div>
            <div
              role="group"
              aria-label="Temas generales"
              className="grid grid-cols-2 gap-1.5 sm:grid-cols-3"
            >
              {/* El tema se pinta del color de su subdivisión: se reconocen igual. */}
              {topics.map((concept) => (
                <Tile
                  key={concept.id}
                  label={concept.name}
                  color={concept.color}
                  pressed={conceptIds.includes(concept.id)}
                  title={`${concept.name}: ${concept.keywords.slice(0, TITLE_KEYWORDS).join(', ')}…`}
                  onClick={() => {
                    toggleConcept(concept.id);
                  }}
                />
              ))}
            </div>
          </section>
        )}

        <div className="flex items-center gap-3 border-t border-sky-400/10 pt-3">
          <a
            href="#/conceptos"
            onClick={onClose}
            className="text-[11px] text-sky-300 hover:text-sky-100 focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            Editar subdivisiones y palabras clave
          </a>
          <button
            type="button"
            onClick={onClose}
            className="hud-btn hud-btn--solid ml-auto px-6 py-2.5 text-[11px]"
          >
            Listo
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
