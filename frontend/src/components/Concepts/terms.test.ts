import { describe, expect, it } from 'vitest';

import { addTerms, normalizeTerm, termWarning } from './terms';

describe('normalizeTerm', () => {
  it('ignora mayúsculas, acentos y espacios repetidos, pero conserva la Ñ', () => {
    expect(normalizeTerm('  Hackéo ')).toBe('HACKEO');
    expect(normalizeTerm('filtración  de   datos')).toBe('FILTRACION DE DATOS');
    expect(normalizeTerm('niño')).toBe('NIÑO');
    expect(normalizeTerm('pingüino')).toBe('PINGUINO');
  });
});

describe('addTerms', () => {
  it('agrega varias separadas por coma o renglón, sin repetir', () => {
    expect(addTerms(['hackeo'], 'Hackéo, phishing\nransomware ,  ,phishing')).toEqual([
      'hackeo',
      'phishing',
      'ransomware',
    ]);
  });

  it('limpia espacios dentro de la frase', () => {
    expect(addTerms([], '  robo   de auto ')).toEqual(['robo de auto']);
  });
});

describe('termWarning', () => {
  it.each([
    ['"hackeo"', 'comillas'],
    ['site:gob.mx', 'dos puntos'],
    ['-curso', 'Exclusiones'],
    ['robo OR asalto', 'OR'],
    ['x', 'Mínimo'],
  ])('avisa de %s', (term, fragment) => {
    expect(termWarning(term)).toContain(fragment);
  });

  it('una frase normal no tiene aviso', () => {
    expect(termWarning('cobro de piso')).toBeNull();
    expect(termWarning('ordenador')).toBeNull();
  });
});
