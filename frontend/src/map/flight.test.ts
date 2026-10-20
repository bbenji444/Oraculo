import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FLIGHT_RESOLUTION_FACTOR, flightPixelRatio, smoothFlights } from './flight';

/** Mapa falso: guarda la resolución y deja disparar `moveend` a mano. */
function fakeMap(initial: number) {
  let ratio = initial;
  const listeners: (() => void)[] = [];
  return {
    redraws: 0,
    getPixelRatio: () => ratio,
    setPixelRatio(value: number) {
      ratio = value;
    },
    redraw() {
      this.redraws += 1;
    },
    once(_type: 'moveend', listener: () => void) {
      listeners.push(listener);
    },
    land() {
      for (const listener of listeners.splice(0)) listener();
    },
  };
}

let frames: FrameRequestCallback[] = [];

beforeEach(() => {
  frames = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function nextFrame() {
  for (const callback of frames.splice(0)) callback(0);
}

describe('resolución durante un vuelo', () => {
  it('es una fracción de la de la pantalla', () => {
    expect(flightPixelRatio(1.25)).toBe(1);
    expect(flightPixelRatio(1)).toBe(FLIGHT_RESOLUTION_FACTOR);
    expect(flightPixelRatio(2)).toBe(1.6);
  });

  it('baja al despegar y vuelve al aterrizar, redibujando en el mismo cuadro', () => {
    const map = fakeMap(1.25);
    const fly = smoothFlights(map, () => 1.25);
    const start = vi.fn();

    fly(2400, start);
    expect(start).toHaveBeenCalledOnce();
    expect(map.getPixelRatio()).toBe(1);

    map.land();
    expect(map.getPixelRatio()).toBe(1);
    nextFrame();
    expect(map.getPixelRatio()).toBe(1.25);
    expect(map.redraws).toBe(1);
  });

  it('si un vuelo interrumpe a otro, la nitidez vuelve hasta el último', () => {
    const map = fakeMap(1.25);
    const fly = smoothFlights(map, () => 1.25);

    fly(2400, () => undefined);
    map.land(); // el segundo vuelo detiene al primero
    fly(1800, () => undefined);
    nextFrame();
    expect(map.getPixelRatio()).toBe(1);

    map.land();
    nextFrame();
    expect(map.getPixelRatio()).toBe(1.25);
  });

  it('sin animación no toca la resolución', () => {
    const map = fakeMap(1.25);
    const start = vi.fn();

    smoothFlights(map, () => 1.25)(0, start);
    expect(start).toHaveBeenCalledOnce();
    expect(map.getPixelRatio()).toBe(1.25);
  });
});
