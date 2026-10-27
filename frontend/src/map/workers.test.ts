import { describe, expect, it } from 'vitest';

import { MAX_MAP_WORKERS, mapWorkerCount } from './workers';

describe('workers del mapa', () => {
  it('usa la mitad de los procesadores, con tope', () => {
    // La computadora de Benji: 16 procesadores lógicos.
    expect(mapWorkerCount(16)).toBe(MAX_MAP_WORKERS);
    expect(mapWorkerCount(4)).toBe(2);
  });

  it('nunca menos de uno, aunque el navegador no diga cuántos hay', () => {
    expect(mapWorkerCount(1)).toBe(1);
    expect(mapWorkerCount(0)).toBe(1);
  });
});
