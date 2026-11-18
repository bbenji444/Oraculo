// @vitest-environment jsdom
/**
 * Radar sobre el globo mientras se busca: la esfera de «Todo el mundo»
 * (ADR-0116) contra la cúpula de una región, que no cambia.
 *
 * La cúpula y la esfera se reemplazan por dobles (no hay WebGL en jsdom) y el
 * mapa es de juguete: se revisa qué se pide al mapa y qué letreros salen.
 */
import { act, cleanup, render } from '@testing-library/react';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Search } from '../../services/searches';
import { ScanOverlay } from './ScanOverlay';

const radar = vi.hoisted(() => {
  const dome = { setBlips: vi.fn(), remove: vi.fn() };
  const shell = { setBlips: vi.fn(), setDaylight: vi.fn(), dissolve: vi.fn(), remove: vi.fn() };
  return {
    dome,
    shell,
    addDomeRadar: vi.fn(() => dome),
    addWorldShell: vi.fn(() => shell),
  };
});

vi.mock('../../map/radar/dome', () => ({ addDomeRadar: radar.addDomeRadar }));
vi.mock('../../map/radar/shell', () => ({
  addWorldShell: radar.addWorldShell,
  SHELL_ALTITUDE_SHARE: 0.06,
}));

// focus_bbox de las regiones (migración 0048 y catálogo de INEGI).
const WORLD_FOCUS: [number, number, number, number] = [-180, -58, 180, 75];
const JALISCO_FOCUS: [number, number, number, number] = [-105.7, 18.9, -101.5, 22.75];
// Espera de ScanOverlay antes de apuntar la cámara a la cúpula, con aire.
const AFTER_AIM_MS = 1000;

function search(overrides: Partial<Search> = {}): Search {
  return {
    search_id: 's1',
    status: 'running',
    region_id: 14,
    region_code: '14',
    region_name: 'Jalisco',
    date_from: '2026-11-18',
    date_to: '2026-11-18',
    concepts: [{ id: 13, name: 'Hackeo de bases de datos' }],
    progress: { stage: 'collect', articles: 12, reused: 0, enriched: 0 },
    queries_planned: 3,
    credits_estimated: 0,
    credits_used: 0,
    llm_tokens_in: 0,
    llm_tokens_out: 0,
    llm_cost_usd: 0,
    results_count: 0,
    error_summary: null,
    created_at: '2026-11-18T19:00:00Z',
    started_at: '2026-11-18T19:00:00Z',
    finished_at: null,
    trigger: 'manual',
    scheduled_for: null,
    ...overrides,
  };
}

const world = (overrides: Partial<Search> = {}) =>
  search({ region_id: 9001, region_code: 'WLD', region_name: 'Mundo', ...overrides });

/**
 * Mapa de juguete: el globo se ve centrado en (640, 400) con radio 300 px,
 * con una proyección ortográfica alrededor del centro de la cámara.
 */
function toyMap() {
  const center = { lng: -35, lat: 20 };
  const DEG = Math.PI / 180;
  const map = {
    on: vi.fn(),
    off: vi.fn(),
    once: vi.fn<(type: string, handler: () => void) => void>(),
    isMoving: vi.fn(() => false),
    flyTo: vi.fn(),
    easeTo: vi.fn(),
    getPitch: vi.fn(() => 60),
    getZoom: vi.fn(() => 2),
    cameraForBounds: vi.fn(() => ({ zoom: 5 })),
    getCenter: vi.fn(() => center),
    getContainer: vi.fn(() => ({ clientWidth: 1280, clientHeight: 800 })),
    project: vi.fn(([lng, lat]: [number, number]) => {
      const [l, p, l0, p0] = [lng * DEG, lat * DEG, center.lng * DEG, center.lat * DEG];
      return {
        x: 640 + 300 * Math.cos(p) * Math.sin(l - l0),
        y: 400 - 300 * (Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l - l0)),
      };
    }),
  };
  return { map, asMap: map as unknown as MapLibreMap };
}

/** Deja correr el temporizador y los cuadros pendientes (letreros y vuelo). */
async function settle(ms = AFTER_AIM_MS) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers({
    toFake: ['setTimeout', 'clearTimeout', 'requestAnimationFrame', 'cancelAnimationFrame'],
  });
  vi.clearAllMocks();
  radar.addDomeRadar.mockImplementation(() => radar.dome);
  radar.addWorldShell.mockImplementation(() => radar.shell);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('ScanOverlay en «Todo el mundo» (ADR-0116)', () => {
  it('envuelve la Tierra con la esfera, sin cúpula ni vuelo ni inclinación', async () => {
    const { map, asMap } = toyMap();
    const { container } = render(
      <ScanOverlay
        search={world()}
        notice={null}
        right={0}
        bottom={120}
        map={asMap}
        regionBbox={WORLD_FOCUS}
      />,
    );
    await settle();

    expect(radar.addWorldShell).toHaveBeenCalledTimes(1);
    expect(radar.addDomeRadar).not.toHaveBeenCalled();
    expect(radar.shell.setBlips).toHaveBeenCalledWith(12);
    expect(map.flyTo).not.toHaveBeenCalled();
    expect(map.easeTo).not.toHaveBeenCalled();
    const text = container.textContent;
    expect(text).toContain('Barrido en curso · Todo el mundo');
    expect(text).toContain('Cobertura global · noticias en español');
    expect(text).toContain('12 notas detectadas');
    // Ni las coordenadas del centro del rectángulo (que caía en Ghana).
    expect(text).not.toContain('8.50° N');
    // Los letreros van sobre el borde de arriba de la esfera, al centro del globo.
    const labels = container.querySelector<HTMLElement>('.mando-shell-labels');
    expect(Number.parseFloat(labels?.style.left ?? '')).toBeCloseTo(640, 0);
    // Borde de arriba de la esfera: 400 − 300 × 1.06 = 82 px (sin subir al encabezado).
    expect(labels?.getAttribute('style')).toContain('max(82px');
  });

  it('al terminar la esfera se disuelve sola y la cámara no se toca', async () => {
    const { map, asMap } = toyMap();
    const { rerender, container } = render(
      <ScanOverlay search={world()} notice={null} right={0} bottom={120} map={asMap} />,
    );
    await settle();
    rerender(
      <ScanOverlay
        search={world({ status: 'completed', results_count: 56 })}
        notice={{ tone: 'ok', text: 'Búsqueda lista: 56 notas' }}
        right={432}
        bottom={104}
        map={asMap}
      />,
    );
    await settle();

    expect(radar.shell.dissolve).toHaveBeenCalledTimes(1);
    expect(radar.shell.remove).not.toHaveBeenCalled();
    expect(map.easeTo).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain('Barrido en curso');
    expect(container.textContent).toContain('BARRIDO COMPLETO');
  });

  it('si la tarjeta de video no puede con la esfera, pone el radar plano sobre el globo', async () => {
    radar.addWorldShell.mockImplementation(() => {
      throw new Error('Sin WebGL 2');
    });
    const { asMap } = toyMap();
    const { container } = render(
      <ScanOverlay search={world()} notice={null} right={0} bottom={120} map={asMap} />,
    );
    await settle();

    const flat = container.querySelector<HTMLElement>('.mando-scan');
    expect(flat).not.toBeNull();
    expect(Number.parseFloat(flat?.style.left ?? '')).toBeCloseTo(640, 0);
    expect(Number.parseFloat(flat?.style.top ?? '')).toBeCloseTo(400, 0);
    // Del tamaño de la esfera: 2 × 300 px × 1.06.
    expect(Number.parseFloat(flat?.style.width ?? '0')).toBeCloseTo(636, 0);
    expect(container.textContent).toContain('Barrido en curso · Todo el mundo');
    expect(container.textContent).toContain('Cobertura global · noticias en español');
  });

  it('en el radar plano los letreros no se meten bajo el encabezado ni la consola', async () => {
    radar.addWorldShell.mockImplementation(() => {
      throw new Error('Sin WebGL 2');
    });
    const { asMap } = toyMap();
    const { container } = render(
      <ScanOverlay search={world()} notice={null} right={0} bottom={120} map={asMap} />,
    );
    await settle();

    // Colgados del radar (arriba y abajo a −9 %) quedaban en ≈ 25 px, detrás del
    // encabezado, y en ≈ 775 px, detrás de la consola (revisión del 18/11/2026).
    const flat = container.querySelector<HTMLElement>('.mando-scan');
    expect(flat?.querySelector('.mando-scan-label')).toBeNull();
    expect(flat?.querySelector('.mando-scan-status')).toBeNull();
    // Van en el mismo bloque que con la esfera, con su tope bajo el encabezado.
    const labels = container.querySelector<HTMLElement>('.mando-shell-labels');
    expect(labels?.getAttribute('style')).toContain('max(82px, calc(var(--header-h) + 4.5rem))');
    expect(labels?.textContent).toContain('Barrido en curso · Todo el mundo');
    expect(labels?.textContent).toContain('Cobertura global · noticias en español');
    expect(labels?.textContent).toContain('12 notas detectadas');
  });

  it('si la esfera falla ya puesta (shaders), cambia al radar plano sobre el globo', async () => {
    const { asMap } = toyMap();
    const { container } = render(
      <ScanOverlay search={world()} notice={null} right={0} bottom={120} map={asMap} />,
    );
    await settle();
    expect(container.querySelector('.mando-scan')).toBeNull();

    // La esfera avisa desde su `render` (no compiló el shader): onFailure.
    const options = (radar.addWorldShell.mock.calls[0] as unknown[] | undefined)?.[1] as
      { onFailure?: () => void } | undefined;
    expect(options?.onFailure).toBeTypeOf('function');
    await act(async () => {
      options?.onFailure?.();
      await Promise.resolve();
    });
    await settle();

    const flat = container.querySelector<HTMLElement>('.mando-scan');
    expect(flat).not.toBeNull();
    expect(Number.parseFloat(flat?.style.left ?? '')).toBeCloseTo(640, 0);
    expect(Number.parseFloat(flat?.style.top ?? '')).toBeCloseTo(400, 0);
    expect(Number.parseFloat(flat?.style.width ?? '0')).toBeCloseTo(636, 0);
    expect(container.querySelector('.mando-shell-labels')?.getAttribute('style')).toContain(
      'max(82px',
    );
  });

  it('con el estilo a medio cargar pone la esfera en cuanto termina de cargar', async () => {
    radar.addWorldShell.mockImplementationOnce(() => {
      throw new Error('Style is not done loading.');
    });
    const { map, asMap } = toyMap();
    const { container } = render(
      <ScanOverlay search={world()} notice={null} right={0} bottom={120} map={asMap} />,
    );
    await settle();
    expect(container.querySelector('.mando-scan')).not.toBeNull();

    const styleLoaded = map.once.mock.calls.find(([type]) => type === 'style.load')?.[1];
    expect(styleLoaded).toBeDefined();
    await act(async () => {
      styleLoaded?.();
      await Promise.resolve();
    });

    expect(radar.addWorldShell).toHaveBeenCalledTimes(2);
    expect(container.querySelector('.mando-scan')).toBeNull();
    expect(container.querySelector('.mando-shell-labels')).not.toBeNull();
  });
});

describe('ScanOverlay en una región (la cúpula no cambia)', () => {
  it('pone la cúpula, vuela a la zona y se inclina; al terminar se endereza', async () => {
    const { map, asMap } = toyMap();
    const { rerender, container } = render(
      <ScanOverlay
        search={search()}
        notice={null}
        right={0}
        bottom={120}
        map={asMap}
        regionBbox={JALISCO_FOCUS}
      />,
    );
    await settle();

    expect(radar.addDomeRadar).toHaveBeenCalledTimes(1);
    expect(radar.addWorldShell).not.toHaveBeenCalled();
    expect(map.flyTo).toHaveBeenCalledWith(expect.objectContaining({ pitch: 60 }));
    expect(container.textContent).toContain('Barrido en curso · Jalisco');
    rerender(
      <ScanOverlay
        search={search({ status: 'completed', results_count: 56 })}
        notice={{ tone: 'ok', text: 'Búsqueda lista: 56 notas' }}
        right={432}
        bottom={104}
        map={asMap}
        regionBbox={JALISCO_FOCUS}
      />,
    );

    expect(radar.dome.remove).toHaveBeenCalledTimes(1);
    expect(map.easeTo).toHaveBeenCalledWith(expect.objectContaining({ pitch: 0 }));
  });
});
