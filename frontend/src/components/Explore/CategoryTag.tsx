/**
 * Etiqueta pequeña con la categoría (el delito) de una nota, que eligió la IA
 * (F12.4, ADR-0029). La usan la fila de la lista (`StoryCard`) y la ficha
 * (`NewsCard`). Al pasar el mouse dice la etiqueta libre que propuso la IA
 * («robo de combustible»), que sirve para decidir las categorías definitivas.
 *
 * No hace: no pinta colores ni símbolos (se definen después, con datos) y no
 * aparece si la nota todavía no tiene categoría.
 */
import type { Article } from '../../services/searches';

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
  return (
    <span
      title={raw ? `Categoría de la IA · «${raw}»` : 'Categoría de la IA'}
      className={`inline-block max-w-full truncate rounded border border-white/15 align-middle text-slate-300 ${
        size === 'row' ? 'px-1 text-[10px]' : 'px-1.5 py-0.5 text-[11px]'
      }`}
    >
      {category.name}
    </span>
  );
}
