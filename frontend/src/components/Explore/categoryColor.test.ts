/** Color de cada tipo de noticia (categoría, migración 0032). */
import { describe, expect, it } from 'vitest';

import { categoryColor, NO_CATEGORY_COLOR } from './categoryColor';

describe('categoryColor', () => {
  it('usa el color de la categoría y, si no tiene, el gris', () => {
    expect(categoryColor({ color: '#FF4D6D' })).toBe('#FF4D6D');
    expect(categoryColor({ color: null })).toBe(NO_CATEGORY_COLOR);
    expect(categoryColor(null)).toBe(NO_CATEGORY_COLOR);
    expect(categoryColor(undefined)).toBe(NO_CATEGORY_COLOR);
  });
});
