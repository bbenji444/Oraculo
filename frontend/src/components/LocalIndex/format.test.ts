import { describe, expect, it } from 'vitest';

import { formatMexicoCity } from './format';

describe('formatMexicoCity', () => {
  it('muestra la hora de la Ciudad de México, no la UTC', () => {
    // 22:31 UTC = 16:31 en la CDMX (UTC-6, sin horario de verano).
    expect(formatMexicoCity('2026-10-16T22:31:00Z')).toBe('16/10/2026, 16:31');
  });
});
