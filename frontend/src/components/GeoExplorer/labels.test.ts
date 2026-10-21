import { describe, expect, it } from 'vitest';

import { LEVEL_LABEL, stateOf } from './labels';

describe('labels', () => {
  it('niveles en español', () => {
    expect(Object.values(LEVEL_LABEL)).toEqual(['País', 'Estado', 'Municipio', 'Localidad']);
  });
});

describe('estado de un resultado del buscador', () => {
  const states = [
    { code: '05', name: 'Coahuila de Zaragoza' },
    { code: '19', name: 'Nuevo León' },
  ];

  it('distingue homónimos por la clave INEGI: San Pedro de Coahuila y el de Nuevo León', () => {
    // Prueba operativa del 20/10/2026: "Municipio San Pedro · 05033" no decía
    // de qué estado era.
    expect(stateOf({ level: 'municipality', code: '05033', country_code: 'MEX' }, states)).toBe(
      'Coahuila de Zaragoza',
    );
    expect(stateOf({ level: 'locality', code: '190390001', country_code: 'MEX' }, states)).toBe(
      'Nuevo León',
    );
  });

  it('países, estados, claves desconocidas o estados sin cargar no llevan estado', () => {
    expect(stateOf({ level: 'state', code: '19', country_code: 'MEX' }, states)).toBeNull();
    expect(stateOf({ level: 'country', code: 'FRA', country_code: 'FRA' }, states)).toBeNull();
    expect(
      stateOf({ level: 'municipality', code: '99001', country_code: 'MEX' }, states),
    ).toBeNull();
    expect(
      stateOf({ level: 'municipality', code: '05033', country_code: 'MEX' }, undefined),
    ).toBeNull();
  });
});
