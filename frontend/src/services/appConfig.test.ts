/** Configuración pública y el botón de regreso a Oráculo (09/11/2026). */
import { describe, expect, it } from 'vitest';

import { safeOraculoUrl } from './appConfig';

describe('safeOraculoUrl', () => {
  it('acepta direcciones http y https', () => {
    expect(safeOraculoUrl('http://172.25.18.234')).toBe('http://172.25.18.234/');
    expect(safeOraculoUrl('https://oraculo.ejemplo.mx/inicio')).toBe(
      'https://oraculo.ejemplo.mx/inicio',
    );
  });

  it('sin dirección o con una peligrosa, no hay botón', () => {
    expect(safeOraculoUrl(null)).toBeNull();
    expect(safeOraculoUrl('')).toBeNull();
    expect(safeOraculoUrl('javascript:alert(1)')).toBeNull();
    expect(safeOraculoUrl('no es una dirección')).toBeNull();
  });
});
