import { describe, expect, it } from 'vitest';

import {
  ARTICLE_ZOOM,
  AURA_FULL_ZOOM,
  AURA_GONE_ZOOM,
  auraOpacity,
  articleOffset,
  articleZoom,
  CALLOUT_WIDTH,
  calloutWidth,
  DESKTOP_ARTICLE_OFFSET,
  flyPadding,
  globeCamera,
  MIN_FRAME_PX,
  MIN_FRAME_ZOOM,
  PANEL_CLEARANCE_PX,
  ringAround,
  WORLD_DETAIL_MAX_ZOOM,
} from './framing';

const DEG = Math.PI / 180;

const LAPTOP = { width: 1366, height: 650 };
const PHONE = { width: 375, height: 812 };

describe('márgenes al volar a una región', () => {
  it('en escritorio deja libre el panel abierto, y nada de gráficas a la derecha', () => {
    const open = flyPadding(LAPTOP, true);
    const closed = flyPadding(LAPTOP, false);

    expect(open.left).toBe(PANEL_CLEARANCE_PX);
    expect(open.right).toBeLessThan(open.left);
    expect(closed.left).toBe(closed.right);
  });

  it('en celular los márgenes caben en la pantalla (antes sumaban 760 px)', () => {
    const padding = flyPadding(PHONE, true);

    expect(padding.left + padding.right).toBeLessThanOrEqual(PHONE.width - MIN_FRAME_PX);
    expect(padding.top + padding.bottom).toBeLessThanOrEqual(PHONE.height - MIN_FRAME_PX);
  });

  it('en una ventana muy baja los márgenes se reducen en proporción', () => {
    const padding = flyPadding({ width: 1000, height: 300 }, true);

    expect(padding.top + padding.bottom).toBeLessThanOrEqual(300 - MIN_FRAME_PX);
    expect(padding.top).toBeGreaterThan(0);
    expect(padding.bottom).toBeGreaterThan(padding.top);
  });
});

describe('nota elegida', () => {
  it('en escritorio el punto va a la izquierda; en celular, abajo y al centro', () => {
    expect(articleOffset(LAPTOP)).toEqual(DESKTOP_ARTICLE_OFFSET);
    const [x, y] = articleOffset(PHONE);

    expect(x).toBe(0);
    expect(y).toBeGreaterThan(0);
  });

  it('la ficha se angosta solo si no cabe', () => {
    expect(calloutWidth(LAPTOP)).toBe(CALLOUT_WIDTH);
    expect(calloutWidth({ width: 320, height: 640 })).toBe(296);
  });
});

describe('encuadre en el globo', () => {
  const screen = { width: 1920, height: 879 };
  const padding = flyPadding(screen, true);
  const rad = Math.PI / 180;

  /** Dónde cae el rectángulo en pantalla con esa cámara (vista ortográfica). */
  function project(
    box: [number, number, number, number],
    camera: { center: number[]; zoom: number },
  ) {
    const [lng0 = 0, lat0 = 0] = camera.center;
    const radius = (512 * 2 ** camera.zoom) / (2 * Math.PI * Math.cos(lat0 * rad));
    const [west, south, east, north] = box;
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = 0; i <= 16; i += 1) {
      const t = i / 16;
      for (const [lng, lat] of [
        [west + (east - west) * t, south],
        [west + (east - west) * t, north],
        [west, south + (north - south) * t],
        [east, south + (north - south) * t],
      ] as const) {
        const dl = (lng - lng0) * rad;
        xs.push(screen.width / 2 + radius * Math.cos(lat * rad) * Math.sin(dl));
        ys.push(
          screen.height / 2 -
            radius *
              (Math.cos(lat0 * rad) * Math.sin(lat * rad) -
                Math.sin(lat0 * rad) * Math.cos(lat * rad) * Math.cos(dl)),
        );
      }
    }
    return {
      left: Math.min(...xs),
      right: Math.max(...xs),
      top: Math.min(...ys),
      bottom: Math.max(...ys),
    };
  }

  it('en una región chica da lo mismo que el mapa plano (Jalisco ≈ 6.9)', () => {
    const camera = globeCamera([-105.7, 18.9, -101.5, 22.75], screen, padding, 7);

    expect(camera.zoom).toBeGreaterThan(6.8);
    expect(camera.zoom).toBeLessThan(7);
  });

  it('la región queda dentro del espacio libre, también en un país grande', () => {
    // Canadá y Rusia se salían ~30 px al desplazar la imagen en vez de la cámara.
    for (const box of [
      [-141, 41.7, -52.6, 83.1],
      [27.3, 41.2, 180, 81.3],
      [-105.7, 18.9, -101.5, 22.75],
    ] as const) {
      const camera = globeCamera([...box], screen, padding, 7);
      const onScreen = project([...box], camera);

      expect(onScreen.left).toBeGreaterThanOrEqual(padding.left - 1);
      expect(onScreen.right).toBeLessThanOrEqual(screen.width - padding.right + 1);
      expect(onScreen.top).toBeGreaterThanOrEqual(padding.top - 1);
      expect(onScreen.bottom).toBeLessThanOrEqual(screen.height - padding.bottom + 1);
    }
  });

  it('una región mediana queda centrada en el espacio libre', () => {
    // En países del tamaño de Rusia el centro puede quedar ~100 px corrido
    // (la esfera se ve de lado), pero siempre completo.
    for (const box of [
      [-105.7, 18.9, -101.5, 22.75],
      [-4.8, 41.4, 9.6, 51.1],
    ] as const) {
      const onScreen = project([...box], globeCamera([...box], screen, padding, 7));
      const freeX = (padding.left + screen.width - padding.right) / 2;
      const freeY = (padding.top + screen.height - padding.bottom) / 2;

      expect(Math.abs((onScreen.left + onScreen.right) / 2 - freeX)).toBeLessThan(20);
      expect(Math.abs((onScreen.top + onScreen.bottom) / 2 - freeY)).toBeLessThan(20);
    }
  });

  it('un punto se acerca al zoom máximo y queda en el espacio libre', () => {
    const camera = globeCamera([-99.13, 19.43, -99.13, 19.43], screen, padding, 14);
    const onScreen = project([-99.13, 19.43, -99.13, 19.43], camera);

    expect(camera.zoom).toBe(14);
    expect(onScreen.left).toBeCloseTo((padding.left + screen.width - padding.right) / 2, 0);
  });

  it('Canadá no se centra en el Ártico ni se aleja de más', () => {
    // cameraForBounds de MapLibre: centro a 70.8° N y zoom 1.69.
    const camera = globeCamera([-141, 41.7, -52.6, 83.1], screen, padding, 6);

    expect(camera.center[1]).toBeGreaterThan(50);
    expect(camera.center[1]).toBeLessThan(66);
    expect(camera.zoom).toBeGreaterThan(2);
  });

  it('Francia continental se acerca; una región que cruza el meridiano 180 también', () => {
    const france = globeCamera([-4.8, 41.4, 9.6, 51.1], screen, padding, 6);
    const fiji = globeCamera([176, -20, -178, -15], screen, padding, 6);

    expect(france.zoom).toBeGreaterThan(4.5);
    expect(Math.abs(fiji.center[0])).toBeGreaterThan(175);
    expect(fiji.zoom).toBeGreaterThan(4);
  });

  it('nunca pasa del zoom máximo del nivel', () => {
    expect(globeCamera([-99.2, 19.3, -99.1, 19.4], screen, padding, 7).zoom).toBe(7);
  });

  it('el mundo entero muestra el globo completo en el espacio libre', () => {
    const freeHeight = screen.height - padding.top - padding.bottom;
    const wholeGlobe = Math.log2(((freeHeight / 2) * 2 * Math.PI) / 512);

    const world = globeCamera([-180, -85, 180, 85], screen, padding, 6).zoom;

    expect(world).toBeLessThanOrEqual(wholeGlobe);
    expect(world).toBeGreaterThan(wholeGlobe - 0.1);
    expect(globeCamera([-180, -85, 180, 85], { width: 300, height: 260 }, padding, 6).zoom).toBe(
      MIN_FRAME_ZOOM,
    );
  });
});

describe('zoom al volar a una nota', () => {
  const CDMX = [-99.13, 19.43] as const;
  const PARIS = [2.35, 48.86] as const;

  it('depende solo de la precisión, no de dónde esté la cámara', () => {
    expect(articleZoom('locality', ...CDMX)).toBe(ARTICLE_ZOOM.locality);
    expect(articleZoom('municipality', ...CDMX)).toBeGreaterThan(articleZoom('state', ...CDMX));
    expect(articleZoom('state', ...CDMX)).toBeGreaterThan(articleZoom('country', ...CDMX));
    expect(articleZoom('unknown', ...CDMX)).toBe(ARTICLE_ZOOM.state);
  });

  it('fuera de México no se acerca más de lo que alcanza el mapa del mundo', () => {
    // París a zoom 11 quedaba vacío: el detalle de calles solo es de México.
    expect(articleZoom('locality', ...PARIS)).toBe(WORLD_DETAIL_MAX_ZOOM);
    expect(articleZoom('country', ...PARIS)).toBe(ARTICLE_ZOOM.country);
  });
});

describe('aureola del globo', () => {
  it('se ve completa con el globo entero y se apaga al acercarse', () => {
    expect(auraOpacity(1.8)).toBe(1);
    expect(auraOpacity(AURA_FULL_ZOOM)).toBe(1);
    expect(auraOpacity((AURA_FULL_ZOOM + AURA_GONE_ZOOM) / 2)).toBeCloseTo(0.5);
    expect(auraOpacity(AURA_GONE_ZOOM)).toBe(0);
    expect(auraOpacity(10)).toBe(0);
  });

  it('el anillo queda a la distancia pedida, empezando por el norte', () => {
    const ring = ringAround([-99, 19], 60, 8);
    expect(ring).toHaveLength(8);
    expect(ring[0]?.[0]).toBeCloseTo(-99);
    expect(ring[0]?.[1]).toBeCloseTo(79);
    // El segundo cuarto del anillo va hacia el este.
    expect(ring[2]?.[0]).toBeGreaterThan(-99);
    for (const [lng, lat] of ring) {
      // Distancia sobre la esfera (ley de cosenos), en grados.
      const cosD =
        Math.sin(19 * DEG) * Math.sin(lat * DEG) +
        Math.cos(19 * DEG) * Math.cos(lat * DEG) * Math.cos((lng + 99) * DEG);
      expect(Math.acos(cosD) / DEG).toBeCloseTo(60);
    }
  });
});
