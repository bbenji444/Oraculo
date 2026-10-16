import { describe, expect, it } from 'vitest';

import { codeLabel, formatPoint, LEVEL_LABEL } from './labels';

describe('labels', () => {
  it('niveles en español', () => {
    expect(Object.values(LEVEL_LABEL)).toEqual(['País', 'Estado', 'Municipio', 'Localidad']);
  });

  it('los países usan código ISO; lo demás, clave INEGI', () => {
    expect(codeLabel('country')).toBe('Código ISO');
    expect(codeLabel('municipality')).toBe('Clave INEGI');
  });

  it('coordenadas con hemisferio en español (O = oeste)', () => {
    expect(formatPoint(-99.148171, 19.432976)).toBe('19.4330° N, 99.1482° O');
    expect(formatPoint(151.2, -33.86)).toBe('33.8600° S, 151.2000° E');
  });
});
