/** Cálculos del menú desplegable: teclado, búsqueda al escribir y dónde abre. */
import { describe, expect, it } from 'vitest';

import { foldText, matchTypeahead, MENU_MAX_HEIGHT, menuPlacement, moveIndex } from './select';

describe('moveIndex', () => {
  it('se mueve sin dar la vuelta', () => {
    expect(moveIndex(0, 1, 5)).toBe(1);
    expect(moveIndex(0, -1, 5)).toBe(0);
    expect(moveIndex(4, 1, 5)).toBe(4);
    expect(moveIndex(2, -5, 5)).toBe(0);
    expect(moveIndex(2, 5, 5)).toBe(4);
    expect(moveIndex(0, 1, 0)).toBe(-1);
  });
});

describe('foldText', () => {
  it('quita acentos y mayúsculas pero conserva la ñ', () => {
    expect(foldText('Michoacán')).toBe('michoacan');
    expect(foldText('Peñón Blanco')).toBe('peñon blanco');
    expect(foldText('ÑUÑOA')).toBe('ñuñoa');
  });
});

describe('matchTypeahead', () => {
  const labels = ['Jalisco', 'México', 'Michoacán', 'Morelos', 'Ñuu Savi'];

  it('salta a la siguiente opción que empieza así, sin importar acentos', () => {
    expect(matchTypeahead(labels, 'm', 0)).toBe(1);
    expect(matchTypeahead(labels, 'm', 1)).toBe(2);
    expect(matchTypeahead(labels, 'mi', 0)).toBe(2);
    expect(matchTypeahead(labels, 'mexico', 4)).toBe(1);
  });

  it('distingue la ñ y no encuentra lo que no hay', () => {
    expect(matchTypeahead(labels, 'ñ', 0)).toBe(4);
    expect(matchTypeahead(labels, 'n', 0)).toBe(-1);
    expect(matchTypeahead(labels, '', 0)).toBe(-1);
  });
});

describe('menuPlacement', () => {
  const viewport = { width: 1200, height: 800 };

  it('abre hacia abajo si cabe', () => {
    const place = menuPlacement({ top: 100, bottom: 140, left: 50, width: 200 }, viewport);
    expect(place.above).toBe(false);
    expect(place.top).toBe(146);
    expect(place.maxHeight).toBe(MENU_MAX_HEIGHT);
    expect(place.minWidth).toBe(200);
  });

  it('abre hacia arriba cerca del borde de abajo', () => {
    const place = menuPlacement({ top: 700, bottom: 740, left: 50, width: 200 }, viewport);
    expect(place.above).toBe(true);
    expect(place.bottom).toBe(106);
  });

  it('no se sale por la derecha', () => {
    const place = menuPlacement({ top: 100, bottom: 140, left: 1150, width: 200 }, viewport);
    expect(place.left).toBe(988);
  });
});
