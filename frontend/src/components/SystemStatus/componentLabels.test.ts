import { describe, expect, it } from 'vitest';

import { componentLabel } from './componentLabels';

describe('componentLabel', () => {
  it('traduce los componentes conocidos', () => {
    expect(componentLabel('database').title).toBe('Base de datos');
    expect(componentLabel('worker').title).toBe('Procesador de búsquedas');
  });

  it('no oculta un componente nuevo: usa su nombre técnico', () => {
    expect(componentLabel('nuevo').title).toBe('nuevo');
  });
});
