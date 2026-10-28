/**
 * Botones de color por categoría (el delito) en el expediente del Centro de
 * mando (Benji, 28/10/2026). Uno por cada categoría que trae la consulta, con
 * su color y cuántas notas tiene, de la que más sale a la que menos.
 *
 * Se prenden y apagan: con «Delincuencia organizada» solo quedan las moradas;
 * con ella y «Huachicol», las de las dos. Sin ninguno prendido se ven todas.
 * El filtro vive en `useTimelineStore`, así que vale igual para la
 * cronología, la lista y los puntos del globo.
 *
 * No hace: no filtra por su cuenta (eso es `applyTimeline`).
 */
import type { CSSProperties } from 'react';

import type { Article } from '../../services/searches';
import { useTimelineStore } from '../../store/timeline';
import { categoryColor } from '../Explore/categoryColor';
import { categoriesIn } from '../Explore/timelineData';

interface CategoryFilterProps {
  /** Las notas de la consulta, antes de este filtro (para contar). */
  articles: readonly Article[];
}

export function CategoryFilter({ articles }: CategoryFilterProps) {
  const picked = useTimelineStore((s) => s.categoryIds);
  const toggle = useTimelineStore((s) => s.toggleCategory);
  const clear = useTimelineStore((s) => s.setCategory);
  const categories = categoriesIn(articles);
  if (categories.length === 0) return null;
  const none = picked.length === 0;
  return (
    // Cuadrícula de tres columnas: siempre ordenada (Benji, 28/10/2026).
    <div role="group" aria-label="Filtrar por categoría" className="grid grid-cols-3 gap-1.5">
      <button
        type="button"
        aria-pressed={none}
        onClick={() => {
          clear(null);
        }}
        className="mando-cat mando-cat--card"
        style={{ '--cat': '148 163 184' } as CSSProperties}
      >
        <span className="mando-cat-name">Todas</span>
      </button>
      {categories.map((category) => {
        const on = picked.includes(category.id);
        const color = categoryColor(category);
        return (
          <button
            key={category.id}
            type="button"
            aria-pressed={on}
            onClick={() => {
              toggle(category.id);
            }}
            title={`${category.name}: ${String(category.count)} notas`}
            // Apagadas se ven tenues cuando hay otra prendida.
            data-dim={!none && !on ? '' : undefined}
            className="mando-cat mando-cat--card"
            style={{ '--cat': hexToRgb(color) } as CSSProperties}
          >
            <span aria-hidden="true" className="mando-cat-dot" />
            <span className="mando-cat-name">{category.name}</span>
            <span className="mando-cat-count">{category.count}</span>
          </button>
        );
      })}
    </div>
  );
}

/** «#A3E635» → «163 230 53», para usarlo con transparencia en el CSS. */
function hexToRgb(hex: string): string {
  const value = hex.replace('#', '');
  const parts = [0, 2, 4].map((i) => Number.parseInt(value.slice(i, i + 2), 16));
  return parts.every((n) => Number.isFinite(n)) ? parts.join(' ') : '148 163 184';
}
