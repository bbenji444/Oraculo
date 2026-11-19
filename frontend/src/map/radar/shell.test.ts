/** Esfera de «Todo el mundo» mientras se busca (ADR-0116). */
import type { Map as MapLibreMap } from 'maplibre-gl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { angularDistance } from './dome';
import {
  addWorldShell,
  CAMERA_FADE_FAR,
  CAMERA_FADE_NEAR,
  cameraDistance,
  cameraFade,
  DISSOLVE_LIFT,
  DISSOLVE_S,
  globeSpots,
  type Ping,
  pingMesh,
  REVEAL_S,
  SHELL_DAY_SHARE,
  SHELL_INTENSITY,
  SHELL_LAYER,
  SHELL_SPOTS,
  shellEnvelope,
  shellIntensity,
  shellMesh,
  spherePoint,
  SPOT_MAX_LAT_DEG,
  VISIBLE_LNG_DEG,
} from './shell';

// Números por vértice: lng, lat, u, t, tipo, nacimiento y semilla.
const STRIDE = 7;
const ATLANTIC: [number, number] = [-35, 20];

describe('malla de la esfera', () => {
  it('va de polo a polo y cierra la costura del antimeridiano', () => {
    const { floats, indices } = shellMesh(4, 8);

    expect(floats.length).toBe(5 * 9 * STRIDE);
    expect(indices.length).toBe(4 * 8 * 6);
    // Primer vértice: polo sur, longitud −180, u = 0 y t = 0.
    expect([floats[0], floats[1], floats[2], floats[3]]).toEqual([-180, -90, 0, 0]);
    // Último: polo norte, longitud 180 (la misma costura), u = 1 y t = 1.
    const last = floats.length - STRIDE;
    expect([floats[last], floats[last + 1], floats[last + 2], floats[last + 3]]).toEqual([
      180, 90, 1, 1,
    ]);
    // Todo es vidrio (tipo 0).
    for (let v = 0; v < floats.length; v += STRIDE) expect(floats[v + 4]).toBe(0);
  });

  it('usa la convención del globo de MapLibre: y al norte, longitud 0 hacia +z', () => {
    const close = (point: number[], expected: number[]) => {
      point.forEach((value, i) => {
        expect(value).toBeCloseTo(expected[i] ?? Number.NaN, 9);
      });
    };
    close(spherePoint(0, 0), [0, 0, 1]);
    close(spherePoint(90, 0), [1, 0, 0]);
    close(spherePoint(0, 90), [0, 1, 0]);
    close(spherePoint(180, 0), [0, 0, -1]);
  });
});

describe('pings (uno por nota encontrada)', () => {
  // Benji, 19/11/2026: «esos puntos de la esfera solo aparecen en una parte
  // del globo. Quiero que aparezcan en todo el globo».
  it('sus lugares cubren todo el planeta, no solo la cara que se ve', () => {
    const spots = globeSpots();

    expect(spots).toHaveLength(SHELL_SPOTS);
    // Ningún punto de la franja queda lejos de un ping.
    let farthest = 0;
    for (let lat = -SPOT_MAX_LAT_DEG; lat <= SPOT_MAX_LAT_DEG; lat += 5) {
      for (let lng = -180; lng < 180; lng += 5) {
        const nearest = Math.min(...spots.map((spot) => angularDistance(spot, [lng, lat])));
        farthest = Math.max(farthest, nearest);
      }
    }
    expect(farthest).toBeLessThan(30);
    for (const spot of spots) {
      expect(Math.abs(spot[1])).toBeLessThanOrEqual(SPOT_MAX_LAT_DEG + 1e-6);
    }
  });

  it('no se amontonan', () => {
    const spots = globeSpots();
    let closest = Number.POSITIVE_INFINITY;
    spots.forEach((a, i) => {
      spots.slice(i + 1).forEach((b) => {
        closest = Math.min(closest, angularDistance(a, b));
      });
    });
    // Cada disco mide ~6° de radio: a más de 15° no se enciman.
    expect(closest).toBeGreaterThan(15);
  });

  it('cada disco lleva el segundo en que se encendió su ping', () => {
    const { floats, indices } = pingMesh([
      { point: ATLANTIC, birth: 5, seed: 0.1 },
      { point: [10, 0], birth: 6, seed: 0.7 },
    ]);

    expect(indices.length).toBeGreaterThan(0);
    expect(floats[4]).toBe(1); // tipo ping
    expect(floats[5]).toBe(5);
    expect(floats[floats.length - STRIDE + 5]).toBe(6);
    expect(pingMesh([]).indices).toHaveLength(0);
  });
});

describe('vida de la esfera: aparición, búsqueda y cierre', () => {
  it('sube del suelo y descubre la rejilla en REVEAL_S', () => {
    const born = shellEnvelope(10, 10, null, false);
    const half = shellEnvelope(10 + REVEAL_S / 2, 10, null, false);
    const up = shellEnvelope(10 + REVEAL_S, 10, null, false);

    expect(born).toEqual({ reveal: 0, lift: 0, fade: 1, flash: 0 });
    expect(half.reveal).toBeCloseTo(0.5);
    expect(half.lift).toBeGreaterThan(half.reveal); // sube rápido y frena arriba
    expect(up).toEqual({ reveal: 1, lift: 1, fade: 1, flash: 0 });
    // Mientras se busca se queda encendida.
    expect(shellEnvelope(500, 10, null, false).fade).toBe(1);
  });

  it('al terminar destella, se expande y se disuelve en DISSOLVE_S', () => {
    const end = 100;
    const start = shellEnvelope(end, 10, end, false);
    const middle = shellEnvelope(end + DISSOLVE_S / 2, 10, end, false);
    const gone = shellEnvelope(end + DISSOLVE_S, 10, end, false);

    expect(start.flash).toBe(1);
    expect(start.fade).toBe(1);
    expect(middle.lift).toBeGreaterThan(1);
    expect(middle.fade).toBeCloseTo(0.5);
    expect(gone.fade).toBe(0);
    expect(gone.flash).toBe(0);
    expect(gone.lift).toBeCloseTo(DISSOLVE_LIFT);
  });

  it('con «Menos movimiento» está quieta y encendida desde el primer cuadro', () => {
    expect(shellEnvelope(0, 0, null, true)).toEqual({ reveal: 1, lift: 1, fade: 1, flash: 0 });
    expect(shellEnvelope(5, 0, 4, true)).toEqual({ reveal: 1, lift: 1, fade: 1, flash: 0 });
  });
});

describe('brillo de la esfera', () => {
  it('saca la distancia de la cámara del plano de recorte de MapLibre', () => {
    expect(cameraDistance([0, 0, 1, -0.2])).toBeCloseTo(5);
    expect(cameraDistance([0, 1, 0, -0.5])).toBeCloseTo(2);
    expect(cameraDistance([0, 0, 1, 0])).toBe(Number.POSITIVE_INFINITY);
  });

  it('se apaga con la cámara muy cerca y es más tenue de día', () => {
    expect(cameraFade(CAMERA_FADE_NEAR)).toBe(0);
    expect(cameraFade(1)).toBe(0);
    expect(cameraFade(CAMERA_FADE_FAR)).toBe(1);
    expect(cameraFade(5)).toBe(1);
    expect(shellIntensity(false, 5)).toBe(SHELL_INTENSITY);
    expect(shellIntensity(true, 5)).toBeCloseTo(SHELL_INTENSITY * SHELL_DAY_SHARE);
    expect(shellIntensity(false, 1.1)).toBe(0);
  });
});

/** Mapa de juguete: solo lo que usa addWorldShell, sin WebGL. */
function toyMap() {
  const layers = new Map<string, unknown>();
  const map = {
    layers,
    addLayer: vi.fn((layer: { id: string }) => {
      layers.set(layer.id, layer);
    }),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
    }),
    getLayer: vi.fn((id: string) => layers.get(id)),
    triggerRepaint: vi.fn(),
    getCenter: vi.fn(() => ({ lng: center[0], lat: center[1] })),
    on: vi.fn((event: string, handler: () => void) => {
      handlers.set(event, handler);
    }),
    off: vi.fn((event: string) => {
      handlers.delete(event);
    }),
  };
  let center: [number, number] = ATLANTIC;
  const handlers = new Map<string, () => void>();
  /** Gira el globo hasta `next` (MapLibre avisa con «move»). */
  const turnTo = (next: [number, number]) => {
    center = next;
    handlers.get('move')?.();
  };
  return { map, asMap: map as unknown as MapLibreMap, turnTo, handlers };
}

/** Los pings que la esfera le pasó a su capa la última vez. */
function lastPings(map: ReturnType<typeof toyMap>['map']): readonly Ping[] {
  const layer = map.layers.get(SHELL_LAYER) as { setPings: (pings: readonly Ping[]) => void };
  const spy = vi.mocked(layer.setPings);
  return spy.mock.calls.at(-1)?.[0] ?? [];
}

function spyPings(map: ReturnType<typeof toyMap>['map']): void {
  const layer = map.layers.get(SHELL_LAYER) as { setPings: (pings: readonly Ping[]) => void };
  vi.spyOn(layer, 'setPings');
}

describe('addWorldShell', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('pone una sola esfera: la de una búsqueda anterior se quita antes', () => {
    const { map, asMap } = toyMap();
    const first = addWorldShell(asMap);
    const firstLayer = map.layers.get(SHELL_LAYER);
    addWorldShell(asMap);

    expect(map.addLayer).toHaveBeenCalledTimes(2);
    expect(map.removeLayer).toHaveBeenCalledTimes(1);
    expect(map.layers.get(SHELL_LAYER)).not.toBe(firstLayer);
    // El cierre tardío de la primera no quita la nueva.
    first.dissolve();
    vi.advanceTimersByTime(DISSOLVE_S * 1000 + 500);
    expect(map.layers.has(SHELL_LAYER)).toBe(true);
  });

  it('al disolverse se quita sola, después del cierre y fuera del cuadro', () => {
    const { map, asMap } = toyMap();
    const shell = addWorldShell(asMap, { animate: true });
    shell.dissolve();

    expect(map.layers.has(SHELL_LAYER)).toBe(true);
    expect(map.triggerRepaint).toHaveBeenCalled();
    vi.advanceTimersByTime(DISSOLVE_S * 1000 - 100);
    expect(map.layers.has(SHELL_LAYER)).toBe(true);
    vi.advanceTimersByTime(400);
    expect(map.layers.has(SHELL_LAYER)).toBe(false);
  });

  it('sin animación aparece y se quita en el acto', () => {
    const { map, asMap } = toyMap();
    const shell = addWorldShell(asMap, { animate: false });
    shell.dissolve();

    expect(map.layers.has(SHELL_LAYER)).toBe(false);
  });

  it('enciende pings al llegar notas y no repite los que ya estaban', () => {
    const { map, asMap } = toyMap();
    const shell = addWorldShell(asMap);
    map.triggerRepaint.mockClear();
    shell.setBlips(3);
    shell.setBlips(3);

    expect(map.triggerRepaint).toHaveBeenCalledTimes(1);
    expect(map.getCenter).toHaveBeenCalledTimes(1);
    shell.remove();
    shell.setBlips(5);
    expect(map.getCenter).toHaveBeenCalledTimes(1);
  });

  it('solo enciende los lugares a la vista; los demás, cuando el giro los trae', () => {
    const { map, asMap, turnTo, handlers } = toyMap();
    const shell = addWorldShell(asMap);
    spyPings(map);
    // Llegan de golpe cientos de notas (la etapa «Fuentes»).
    shell.setBlips(500);

    const first = lastPings(map);
    expect(first.length).toBeGreaterThan(0);
    expect(first.length).toBeLessThan(SHELL_SPOTS);
    const lngGap = (spot: [number, number], lng: number) =>
      Math.abs(((spot[0] - lng + 540) % 360) - 180);
    for (const ping of first) {
      expect(lngGap(ping.point, ATLANTIC[0])).toBeLessThanOrEqual(VISIBLE_LNG_DEG + 1e-6);
    }
    // El primero nace cerca del centro de la vista, para que se vea nacer.
    expect(angularDistance(first[0]?.point ?? [0, -90], ATLANTIC)).toBeLessThan(25);

    // Media vuelta: se encienden los del otro lado y los de antes no se mueven.
    turnTo([145, 20]);
    const later = lastPings(map);
    expect(later.length).toBeGreaterThan(first.length);
    expect(later.slice(0, first.length)).toEqual(first);
    for (const ping of later.slice(first.length)) {
      expect(lngGap(ping.point, 145)).toBeLessThanOrEqual(VISIBLE_LNG_DEG + 1e-6);
    }

    // Una vuelta completa los enciende todos, repartidos por el planeta.
    for (let lng = 145; lng > -215; lng -= 30) turnTo([lng, 20]);
    const all = lastPings(map);
    expect(all).toHaveLength(SHELL_SPOTS);
    expect(new Set(all.map((p) => p.point.join()))).toHaveProperty('size', SHELL_SPOTS);

    shell.remove();
    expect(handlers.has('move')).toBe(false);
  });

  it('nunca enciende más pings que notas encontradas', () => {
    const { map, asMap, turnTo } = toyMap();
    const shell = addWorldShell(asMap);
    spyPings(map);
    shell.setBlips(3);
    for (let lng = 145; lng > -215; lng -= 30) turnTo([lng, 20]);

    expect(lastPings(map)).toHaveLength(3);
    shell.remove();
  });
});
