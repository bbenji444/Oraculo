/**
 * Etiqueta pequeña con la categoría (el delito) de una nota, que eligió la IA
 * (F12.4, ADR-0029), con el color de su categoría (migración 0032): el mismo
 * en la lista, la cronología, la ficha, la barra del expediente y el globo.
 * Al pasar el mouse dice la etiqueta libre que propuso la IA («robo de
 * combustible»).
 *
 * No hace: no aparece si la nota todavía no tiene categoría.
 */
import type { Article } from '../../services/searches';
import { categoryColor } from './categoryColor';

interface CategoryTagProps {
  article: Pick<Article, 'category' | 'category_raw'>;
  /** `row`: la lista, más chica; `card`: la ficha. */
  size?: 'row' | 'card';
}

export function CategoryTag({ article, size = 'row' }: CategoryTagProps) {
  const { category } = article;
  if (!category) {
    return null;
  }
  const raw = article.category_raw;
  const color = categoryColor(category);
  return (
    <span
      title={raw ? `Categoría de la IA · «${raw}»` : 'Categoría de la IA'}
      // El color en el borde, el fondo y el punto; el texto claro para leerse.
      style={{ borderColor: `${color}66`, backgroundColor: `${color}14` }}
      className={`inline-flex min-w-0 max-w-full items-center gap-1 rounded border align-middle text-slate-200 ${
        size === 'row' ? 'px-1 text-[10px]' : 'px-1.5 py-0.5 text-[11px]'
      }`}
    >
      <span
        aria-hidden="true"
        className="size-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: color, boxShadow: `0 0 5px ${color}` }}
      />
      <span className="truncate">{category.name}</span>
    </span>
  );
}
