// @vitest-environment jsdom
/** Red de seguridad de los gráficos 3D: sin WebGL no se queda la pantalla en blanco. */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GlobeUnavailable, GraphicsBoundary } from './GraphicsBoundary';

function BrokenGlobe(): never {
  // Lo que lanza MapLibre cuando Chrome bloqueó WebGL (26/10/2026).
  throw new Error('GPUInitializationError: WebGL2 is required to display this map.');
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('red de seguridad de los gráficos', () => {
  it('si el globo no se puede dibujar, muestra el aviso y lo de alrededor sigue', () => {
    // React y la red escriben el error en la consola: se calla en la prueba.
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(
      <div>
        <p>Panel de búsqueda</p>
        <GraphicsBoundary fallback={<GlobeUnavailable />}>
          <BrokenGlobe />
        </GraphicsBoundary>
      </div>,
    );

    expect(screen.getByRole('alert').textContent).toContain('No se pudo dibujar el globo');
    expect(screen.getByRole('button', { name: 'Recargar' })).toBeTruthy();
    expect(screen.getByText('Panel de búsqueda')).toBeTruthy();
  });

  it('sin errores muestra lo de adentro', () => {
    render(
      <GraphicsBoundary fallback={<GlobeUnavailable />}>
        <p>Globo</p>
      </GraphicsBoundary>,
    );

    expect(screen.getByText('Globo')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
