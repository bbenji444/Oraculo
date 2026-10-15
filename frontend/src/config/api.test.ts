import { describe, expect, it } from 'vitest';

import { apiUrl } from './api';

describe('apiUrl', () => {
  it('antepone el prefijo de la API', () => {
    expect(apiUrl('health')).toBe('/api/v1/health');
  });

  it('acepta rutas con diagonales iniciales sin duplicarlas', () => {
    expect(apiUrl('//regions/search')).toBe('/api/v1/regions/search');
  });

  it('rechaza una ruta vacía', () => {
    expect(() => apiUrl('  /  ')).toThrow('no puede estar vacía');
  });
});
