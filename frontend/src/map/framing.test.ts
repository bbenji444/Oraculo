import { describe, expect, it } from 'vitest';

import {
  articleOffset,
  CALLOUT_WIDTH,
  calloutWidth,
  DESKTOP_ARTICLE_OFFSET,
  flyPadding,
  MIN_FRAME_PX,
  PANEL_CLEARANCE_PX,
} from './framing';

const LAPTOP = { width: 1366, height: 650 };
const PHONE = { width: 375, height: 812 };

describe('márgenes al volar a una región', () => {
  it('en escritorio deja libre el panel abierto, y nada de gráficas a la derecha', () => {
    const open = flyPadding(LAPTOP, true);
    const closed = flyPadding(LAPTOP, false);

    expect(open.left).toBe(PANEL_CLEARANCE_PX);
    expect(open.right).toBeLessThan(open.left);
    expect(closed.left).toBe(closed.right);
  });

  it('en celular los márgenes caben en la pantalla (antes sumaban 760 px)', () => {
    const padding = flyPadding(PHONE, true);

    expect(padding.left + padding.right).toBeLessThanOrEqual(PHONE.width - MIN_FRAME_PX);
    expect(padding.top + padding.bottom).toBeLessThanOrEqual(PHONE.height - MIN_FRAME_PX);
  });

  it('en una ventana muy baja los márgenes se reducen en proporción', () => {
    const padding = flyPadding({ width: 1000, height: 300 }, true);

    expect(padding.top + padding.bottom).toBeLessThanOrEqual(300 - MIN_FRAME_PX);
    expect(padding.top).toBeGreaterThan(0);
    expect(padding.bottom).toBeGreaterThan(padding.top);
  });
});

describe('nota elegida', () => {
  it('en escritorio el punto va a la izquierda; en celular, abajo y al centro', () => {
    expect(articleOffset(LAPTOP)).toEqual(DESKTOP_ARTICLE_OFFSET);
    const [x, y] = articleOffset(PHONE);

    expect(x).toBe(0);
    expect(y).toBeGreaterThan(0);
  });

  it('la ficha se angosta solo si no cabe', () => {
    expect(calloutWidth(LAPTOP)).toBe(CALLOUT_WIDTH);
    expect(calloutWidth({ width: 320, height: 640 })).toBe(296);
  });
});
