/**
 * Color de cada tipo de noticia (categoría, F12.4). Cada categoría trae su
 * color de la base (migración 0032, 28/10/2026); lo usan la barra del
 * expediente, las etiquetas de la lista y de la cronología, y los puntos del
 * globo, para que el mismo delito se vea igual en todos lados.
 *
 * No hace: no inventa colores; si una categoría no tiene, va en gris.
 */
import type { ArticleCategory } from '../../services/searches';

/** Gris para lo que no tiene categoría (o una categoría sin color). */
export const NO_CATEGORY_COLOR = '#94A3B8';

/**
 * @param category La categoría de una nota, o nada.
 * @returns Su color `#RRGGBB`, o el gris si no tiene.
 * @example categoryColor({ color: '#FF4D6D' }) // '#FF4D6D'
 */
export function categoryColor(category: Pick<ArticleCategory, 'color'> | null | undefined): string {
  return category?.color ?? NO_CATEGORY_COLOR;
}
