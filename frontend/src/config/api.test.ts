import { describe, expect, it } from 'vitest';

import { apiUrl, pageBase } from './api';

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

describe('pageBase', () => {
  it('conserva el prefijo del gateway de Oráculo', () => {
    expect(pageBase('https://oraculo.local/m/noticias/', './')).toBe(
      'https://oraculo.local/m/noticias',
    );
  });

  it('ignora la pantalla y el hash de la dirección', () => {
    expect(pageBase('https://oraculo.local/m/noticias/index.html#/casos', './')).toBe(
      'https://oraculo.local/m/noticias',
    );
  });

  it('en acceso directo devuelve el origen', () => {
    expect(pageBase('http://localhost:8080/', './')).toBe('http://localhost:8080');
    expect(pageBase('http://localhost:5173/#/explorar', '/')).toBe('http://localhost:5173');
  });
});
