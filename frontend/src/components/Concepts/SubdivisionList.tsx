/**
 * Lista de las subdivisiones en la pantalla «Conceptos» (Benji, 02/11/2026;
 * ADR-0038): todas, también las apagadas, en el orden del catálogo.
 *
 * Cada renglón dice su color, su nombre, si está apagada y si tiene tema
 * general para buscarla. Al elegir una, se edita en el panel derecho.
 *
 * No hace: no edita; avisa cuál se eligió.
 */
import type { CSSProperties } from 'react';

import type { Category } from '../../services/categories';
import { categoryColor, hexToRgb } from '../Explore/categoryColor';

interface SubdivisionListProps {
  categories: readonly Category[];
  selectedId: number | null;
  onSelect: (category: Category) => void;
}

/** Aviso corto del renglón: «respaldo», «apagada», «sin tema» o nada. */
function statusOf(category: Category): string {
  if (category.is_other) return 'respaldo';
  if (!category.is_active) return 'apagada';
  if (category.topic_concept_id === null) return 'sin tema';
  return '';
}

export function SubdivisionList({ categories, selectedId, onSelect }: SubdivisionListProps) {
  return (
    <ul aria-label="Subdivisiones" className="grid gap-1.5 p-1.5 sm:grid-cols-2">
      {categories.map((category) => (
        <li key={category.id}>
          <button
            type="button"
            aria-pressed={selectedId === category.id}
            onClick={() => {
              onSelect(category);
            }}
            data-dim={category.is_active ? undefined : ''}
            className="mando-cat mando-cat--card w-full"
            style={{ '--cat': hexToRgb(categoryColor(category)) } as CSSProperties}
          >
            <span aria-hidden="true" className="mando-cat-dot" />
            <span className="mando-cat-name">{category.name}</span>
            <span className="shrink-0 text-[10px] text-slate-400">{statusOf(category)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
