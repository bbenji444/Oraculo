/**
 * Ventana «¿Qué rastrear?» del Centro de mando, al centro de la pantalla
 * (Benji, 02/11/2026; ADR-0038). Se abre al tocar la parte 01 de la frase.
 *
 * Una sola lista de delitos y una pregunta (rediseño del 09/11/2026: antes
 * había dos cuadrículas con los mismos delitos, «Homicidio» salía arriba y
 * abajo, y Benji no entendía la diferencia):
 *
 * 1. **¿Relacionados con quién?** La FGR, la Policía de investigación (los
 *    conceptos que no son tema de un delito) o «Con nadie en particular».
 * 2. **¿Qué delitos?** «Todos» o los que se elijan.
 *
 * Lo que se guarda no cambia (el servidor es el mismo):
 * - con alguien: sus conceptos y los delitos como subdivisiones. «FGR ·
 *   Homicidio» trae solo notas con las dos cosas (Benji, 03/11/2026: «es una
 *   súper obligación que tenga que cumplir con ambas condiciones»);
 * - con nadie: el tema general de cada delito, por su cuenta (todos los
 *   homicidios, aparezca o no la FGR). «Todos» no aplica: buscar todos los
 *   delitos de todo el país sin nadie sería enorme.
 *
 * Abajo, una frase dice en palabras qué va a traer la búsqueda.
 *
 * Se cierra con «Listo», con Esc o con un clic en el fondo oscuro.
 *
 * Todo sale de los conceptos: el tema general de un delito trae el id de su
 * subdivisión (`category_id`), su nombre y su color. El catálogo de
 * subdivisiones solo da el orden; si no se pudo leer, se ordena por nombre.
 *
 * No hace: no busca ni decide reglas; escribe en `useExplorerStore` y el
 * servidor valida (una subdivisión sola, sin nadie, no se manda).
 */
import { type CSSProperties, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { useCategories } from '../../hooks/useCategories';
import { useConcepts } from '../../hooks/useConcepts';
import type { Category } from '../../services/categories';
import type { Concept } from '../../services/concepts';
import { useExplorerStore } from '../../store/explorer';
import { hexToRgb } from '../Explore/categoryColor';
import { GLASS } from '../Explore/ui';
import { trackSummary } from './trackSummary';

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
  disabled,
  title,
  onClick,
}: {
  label: string;
  color: string;
  pressed: boolean;
  dim?: boolean;
  disabled?: boolean;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      disabled={disabled}
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
  const setConcepts = useExplorerStore((s) => s.setConcepts);
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
  // Los conceptos que no son tema de un delito: la FGR, la PDI.
  const bases = active.filter((c) => c.category_id === null);
  const topics = topicsOf(active, categories);
  const loading = !concepts;

  const baseIds = new Set(bases.map((c) => c.id));
  const chosenBases = conceptIds.filter((id) => baseIds.has(id));
  const chosenTopicIds = conceptIds.filter((id) => !baseIds.has(id));
  const anchored = chosenBases.length > 0;
  // «Con nadie en particular» se recuerda aunque todavía no haya delito elegido.
  const [noAnchor, setNoAnchor] = useState(!anchored && chosenTopicIds.length > 0);
  const independent = !anchored && (noAnchor || chosenTopicIds.length > 0);

  const conceptOfCrime = new Map(topics.map((t) => [t.category_id, t.id]));
  const crimeOfConcept = new Map(topics.map((t) => [t.id, t.category_id]));
  // Delitos elegidos, por id de subdivisión, en cualquiera de los dos modos.
  const chosenCrimes = anchored
    ? subdivisionIds
    : chosenTopicIds.flatMap((id) => {
        const crime = crimeOfConcept.get(id);
        return crime === undefined ? [] : [crime];
      });
  const topicsFor = (crimes: readonly number[]) =>
    crimes.flatMap((id) => {
      const concept = conceptOfCrime.get(id);
      return concept === undefined ? [] : [concept];
    });

  const toggleBase = (concept: Concept) => {
    setNoAnchor(false);
    if (chosenBases.includes(concept.id)) {
      const rest = chosenBases.filter((id) => id !== concept.id);
      setConcepts(rest);
      // Sin nadie elegido, los delitos ya no filtran a nadie.
      if (rest.length === 0) setSubdivisions([]);
      return;
    }
    if (!anchored) {
      // Venía de «con nadie»: los delitos elegidos pasan a filtrarlo.
      setConcepts([concept.id]);
      setSubdivisions(chosenCrimes);
      return;
    }
    setConcepts([...chosenBases, concept.id]);
  };
  const chooseNoAnchor = () => {
    setNoAnchor(true);
    // Los delitos elegidos siguen, ahora cada uno por su cuenta.
    setConcepts(topicsFor(chosenCrimes));
    setSubdivisions([]);
  };
  const toggleCrime = (crimeId: number) => {
    if (independent) {
      const next = chosenCrimes.includes(crimeId)
        ? chosenCrimes.filter((id) => id !== crimeId)
        : [...chosenCrimes, crimeId];
      setConcepts(topicsFor(next));
      return;
    }
    const first = bases[0];
    if (!anchored) {
      // Un delito sin nadie elegido se busca con el primero (la FGR).
      if (first) setConcepts([first.id]);
      setSubdivisions([crimeId]);
      return;
    }
    // Una búsqueda reabierta podía traer temas sueltos junto a la FGR: se quitan.
    if (chosenTopicIds.length > 0) setConcepts(chosenBases);
    toggleSubdivision(crimeId);
  };

  const anchorNames = bases.filter((c) => chosenBases.includes(c.id)).map((c) => c.name);
  const crimeNames = topics.filter((t) => chosenCrimes.includes(t.category_id)).map((t) => t.name);
  const summary = trackSummary(anchorNames, crimeNames, independent);

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
          <section aria-label="Relacionados con quién" className="space-y-2">
            <p className="hud-label mb-0">1 · ¿Relacionados con quién?</p>
            <div role="group" aria-label="Relacionados con" className="flex flex-wrap gap-2">
              {bases.map((concept) => (
                <button
                  key={concept.id}
                  type="button"
                  aria-pressed={chosenBases.includes(concept.id)}
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
              <button
                type="button"
                aria-pressed={independent}
                onClick={chooseNoAnchor}
                className="mando-cat px-3 py-1.5 text-[12px]"
                style={{ '--cat': hexToRgb('#94A3B8') } as CSSProperties}
              >
                <span aria-hidden="true" className="mando-cat-dot" />
                Con nadie en particular
              </button>
            </div>
          </section>
        )}

        {!loading && topics.length > 0 && (
          <section aria-label="Qué delitos" className="space-y-2 border-t border-sky-400/10 pt-4">
            <p className="hud-label mb-0">2 · ¿Qué delitos?</p>
            <div
              role="group"
              aria-label="Delitos"
              className="grid grid-cols-2 gap-1.5 sm:grid-cols-3"
            >
              <Tile
                label="Todos"
                color="#94A3B8"
                pressed={anchored && chosenCrimes.length === 0}
                disabled={independent}
                title={
                  independent
                    ? 'Con nadie en particular, elige uno o varios delitos'
                    : 'Todo lo de quien elegiste, de cualquier delito'
                }
                onClick={() => {
                  if (!anchored) {
                    const first = bases[0];
                    if (first) setConcepts([first.id]);
                  }
                  setSubdivisions([]);
                }}
              />
              {topics.map((topic) => {
                const on = chosenCrimes.includes(topic.category_id);
                return (
                  <Tile
                    key={topic.category_id}
                    label={topic.name}
                    color={topic.color}
                    pressed={on}
                    dim={chosenCrimes.length > 0 && !on}
                    title={`${topic.name}: ${topic.keywords.slice(0, TITLE_KEYWORDS).join(', ')}…`}
                    onClick={() => {
                      toggleCrime(topic.category_id);
                    }}
                  />
                );
              })}
            </div>
          </section>
        )}

        {!loading && (
          <p
            role="status"
            className="rounded-lg border border-sky-400/20 bg-sky-400/[0.06] px-3 py-2 text-[12px] text-slate-200"
          >
            {summary}
          </p>
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
