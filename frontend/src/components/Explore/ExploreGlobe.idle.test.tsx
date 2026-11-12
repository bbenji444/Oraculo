// @vitest-environment jsdom
/**
 * El globo no vuelve a girar solo antes de 5 minutos (Benji, 11/11/2026).
 *
 * Reproduce el error: esperando el barrido en el Centro de mando, a los 10
 * segundos sin tocar nada el globo empezaba a girar. Lo hacía una regla del
 * 30/10 que seguía viva aparte de `useIdleSpin` (5 minutos).
 *
 * MapLibre se reemplaza por un mapa de mentiras: aquí no importa el dibujo,
 * solo si alguien prende `spinning`.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useExplorerStore } from '../../store/explorer';
import { ExploreGlobe } from './ExploreGlobe';
import { IDLE_SPIN_MS } from './useIdleSpin';

vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}));
vi.mock('../../map/setup', () => ({ setupMapLibre: () => undefined }));
vi.mock('maplibre-gl', () => {
  // Cualquier método existe y no hace nada; los que el globo lee al arrancar
  // devuelven algo con la forma esperada.
  const answers: Record<string, unknown> = {
    getContainer: () => document.createElement('div'),
    getCanvas: () => document.createElement('canvas'),
    getPadding: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
    getCenter: () => ({ lng: 0, lat: 0 }),
    project: () => ({ x: 0, y: 0 }),
    getZoom: () => 1,
    getPitch: () => 0,
    getBearing: () => 0,
    isMoving: () => false,
    isStyleLoaded: () => false,
    getLayer: () => undefined,
    getSource: () => undefined,
    queryRenderedFeatures: () => [],
  };
  // `function` y no flecha: el globo lo llama con `new`.
  const FakeMap = vi.fn(function FakeMap() {
    return new Proxy({}, { get: (_target, prop: string) => answers[prop] ?? (() => undefined) });
  });
  return { Map: FakeMap, NavigationControl: vi.fn() };
});

// Más que los 10 s del Centro de mando y los 25 s del diseño de columna.
const WAIT_MS = 30_000;

describe('giro automático del globo', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // jsdom no trae ResizeObserver; el globo solo lo usa para medir paneles.
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
      },
    );
    // Una búsqueda en curso, con su región elegida (el barrido).
    useExplorerStore.setState({
      motion: 'slow',
      spinning: false,
      searchId: 'barrido',
      regionId: 14,
      articleId: null,
      wallCaseId: null,
    });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it.each([true, false])(
    'esperando el barrido no gira antes de 5 minutos (Centro de mando: %s)',
    (mando) => {
      const client = new QueryClient();
      const { unmount } = render(
        <QueryClientProvider client={client}>
          <ExploreGlobe articles={[]} colors={new Map()} clearHeader={mando} />
        </QueryClientProvider>,
      );

      act(() => {
        vi.advanceTimersByTime(WAIT_MS);
      });

      expect(useExplorerStore.getState().spinning).toBe(false);
      expect(WAIT_MS).toBeLessThan(IDLE_SPIN_MS);
      unmount();
    },
  );
});
