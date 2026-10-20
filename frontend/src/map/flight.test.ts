import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FLIGHT_RESOLUTION_FACTOR, flightPixelRatio, smoothFlights } from './flight';

/** Mapa falso: guarda la resolución y deja disparar `moveend` a mano. */
function fakeMap(initial: number) {
  let ratio = initial;
  const listeners: (() => void)[] = [];
  return {
    redraws: 0,
    /** Lo que hace `start`: con animación, el mapa queda en movimiento. */
    moving: false,
    /** Orden de las llamadas, para comprobar que primero despega. */
    calls: [] as string[],
    isMoving() {
      return this.moving;
    },
    getPixelRatio: () => ratio,
    setPixelRatio(value: number) {
      this.calls.push(`resolución ${String(value)}`);
      ratio = value;
    },
    redraw() {
      this.redraws += 1;
    },
    once(_type: 'moveend', listener: () => void) {
      listeners.push(listener);
    },
    land() {
      this.moving = false;
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

  it('baja ya en vuelo y vuelve al aterrizar, redibujando en el mismo cuadro', () => {
    const map = fakeMap(1.25);
    const fly = smoothFlights(map, () => 1.25);

    fly(2400, () => {
      map.calls.push('despega');
      map.moving = true;
    });
    // Primero despega: con el mapa quieto, MapLibre detendría el vuelo al
    // cambiar la resolución y avisaría "terminó de moverse".
    expect(map.calls).toEqual(['despega', 'resolución 1']);
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

    const takeOff = () => {
      map.moving = true;
    };
    fly(2400, takeOff);
    map.land(); // el segundo vuelo detiene al primero
    fly(1800, takeOff);
    nextFrame();
    expect(map.getPixelRatio()).toBe(1);

    map.land();
    nextFrame();
    expect(map.getPixelRatio()).toBe(1.25);
  });

  it('si saltó sin animar (menos movimiento) no la baja, y devuelve la de un vuelo anterior', () => {
    const map = fakeMap(1.25);
    const fly = smoothFlights(map, () => 1.25);

    fly(2400, () => {
      map.moving = true;
    });
    expect(map.getPixelRatio()).toBe(1);
    map.moving = false;
    fly(2400, () => undefined); // MapLibre saltó: el mapa no se mueve
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
