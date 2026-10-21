/**
 * Guion de cámara del laboratorio del muro: siempre los mismos movimientos,
 * para comparar opciones con números (ADR-0102).
 *
 * 1. **Giro:** el globo gira sobre México (zoom 3.2), como en reposo.
 * 2. **Vuelo:** del globo completo a encuadrar el caso (la cámara de Explorar:
 *    `globeCamera` + `smoothFlights`).
 * 3. **Órbita:** la cámara orbita el primer nodo a zoom 11.5 e inclinada 55°,
 *    como al seleccionar una entidad (plan §9.5).
 * 4. **Cerca:** Polanco a zoom 14: donde `GlobeView` de deck.gl pierde
 *    precisión (su documentación: "no high-precision rendering at zoom > 12").
 *
 * Antes de medir cada paso se espera a que el mapa termine de cargar
 * (`idle`): se mide el dibujo, no la red. El vuelo sí puede cargar teselas.
 *
 * No hace: no dibuja el muro (eso es cada opción).
 */
import type { Map as MapLibreMap } from 'maplibre-gl';

import { smoothFlights } from '../map/flight';
import { flyPadding, globeCamera } from '../map/framing';
import { type FrameStats, frameStats, recordFrames } from './fpsMeter';
import type { LabCase } from './labCase';

export const PHASES = ['giro', 'vuelo', 'orbita', 'cerca'] as const;
export type Phase = (typeof PHASES)[number];

export const PHASE_LABEL: Record<Phase, string> = {
  giro: 'Giro del globo',
  vuelo: 'Vuelo al caso',
  orbita: 'Órbita a un nodo',
  cerca: 'Cerca (zoom 14)',
};

// Duración de cada paso: lo bastante para 200+ cuadros a 60 fps.
const DURATION_MS: Record<Phase, number> = { giro: 5000, vuelo: 3500, orbita: 6000, cerca: 4000 };
const FLIGHT_MS = 3000;
const GLOBE_VIEW = { center: [-102, 23.5] as [number, number], zoom: 2.2, pitch: 0, bearing: 0 };
const POLANCO: [number, number] = [-99.1966, 19.434];
// Si el mapa no termina de cargar en este tiempo, se mide de todos modos.
const IDLE_TIMEOUT_MS = 10_000;

function animate(durationMs: number, step: (progress: number) => void): Promise<void> {
  return new Promise((resolve) => {
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      step(progress);
      if (progress < 1) requestAnimationFrame(tick);
      else resolve();
    };
    requestAnimationFrame(tick);
  });
}

function waitIdle(map: MapLibreMap): Promise<void> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(resolve, IDLE_TIMEOUT_MS);
    map.once('idle', () => {
      window.clearTimeout(timer);
      resolve();
    });
    map.triggerRepaint();
  });
}

function caseBox(labCase: LabCase): [number, number, number, number] {
  const lngs = labCase.nodes.map((n) => n.lng);
  const lats = labCase.nodes.map((n) => n.lat);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

/** Deja la cámara donde empieza el paso y espera a que el mapa cargue. */
async function prepare(map: MapLibreMap, labCase: LabCase, phase: Phase): Promise<void> {
  const focus = labCase.nodes[0];
  if (phase === 'giro' || phase === 'vuelo') map.jumpTo(GLOBE_VIEW);
  if (phase === 'orbita' && focus) {
    map.jumpTo({ center: [focus.lng, focus.lat], zoom: 11.5, pitch: 55, bearing: 0 });
  }
  if (phase === 'cerca') map.jumpTo({ center: POLANCO, zoom: 14, pitch: 50, bearing: 0 });
  await waitIdle(map);
}

async function move(map: MapLibreMap, labCase: LabCase, phase: Phase): Promise<void> {
  const duration = DURATION_MS[phase];
  const focus = labCase.nodes[0];
  if (phase === 'giro') {
    await animate(duration, (p) => {
      map.jumpTo({ ...GLOBE_VIEW, center: [-108 + 14 * p, 23.5], zoom: 3.2 });
    });
  } else if (phase === 'vuelo') {
    const canvas = map.getContainer();
    const screen = { width: canvas.clientWidth, height: canvas.clientHeight };
    const camera = globeCamera(caseBox(labCase), screen, flyPadding(screen, false), 9);
    const fly = smoothFlights(map, () => window.devicePixelRatio);
    fly(FLIGHT_MS, () => {
      map.flyTo({ center: camera.center, zoom: camera.zoom, duration: FLIGHT_MS, essential: true });
    });
    await animate(duration, () => undefined);
  } else if (phase === 'orbita' && focus) {
    await animate(duration, (p) => {
      map.jumpTo({ center: [focus.lng, focus.lat], zoom: 11.5, pitch: 55, bearing: 360 * p });
    });
  } else if (phase === 'cerca') {
    await animate(duration, (p) => {
      map.jumpTo({ center: POLANCO, zoom: 14, pitch: 50, bearing: 40 * p });
    });
  }
}

/**
 * Corre un paso del guion y mide sus cuadros.
 *
 * @param map Mapa con el muro (o sin él, como control).
 * @param labCase Caso dibujado (para encuadrar y orbitar).
 * @param phase Paso del guion.
 * @returns Estadísticas de los cuadros mientras la cámara se movía.
 */
export async function runPhase(
  map: MapLibreMap,
  labCase: LabCase,
  phase: Phase,
): Promise<FrameStats> {
  await prepare(map, labCase, phase);
  const frames = recordFrames(DURATION_MS[phase]);
  await move(map, labCase, phase);
  return frameStats(await frames);
}
