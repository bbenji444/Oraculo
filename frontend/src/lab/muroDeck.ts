/**
 * Opción B del ADR-0102: el muro con deck.gl 9.4 sobre el mismo globo.
 *
 * `MapLibreOverlay` (de `@deck.gl/maplibre`, el que la documentación de deck.gl
 * pide para MapLibre v6) en modo **entrelazado**: comparte el contexto WebGL de
 * MapLibre, así que es un solo lienzo y la cámara va sincronizada.
 *
 * - **Arcos:** dos `PathLayer` con la misma geometría que la opción A
 *   (`arcPath`, gran círculo con altura): una ancha y tenue (halo) y una delgada
 *   y brillante (núcleo), con mezcla aditiva. Los sugeridos van más tenues: el
 *   punteado de deck.gl está en `@deck.gl/extensions`, que no se instaló.
 * - **Luz que recorre el arco:** un `ScatterplotLayer` de "cometas" cuya
 *   posición se recalcula en cada cuadro (sin `TripsLayer`: está en
 *   `geo-layers`, descartado por sus vulnerabilidades).
 * - **Nodos:** `ScatterplotLayer` de halo que late y de núcleo con borde de
 *   estatus legal.
 *
 * En el globo, deck.gl pide `cullMode: 'none'` para que los arcos no
 * desaparezcan según el ángulo (documentación de `ArcLayer`, "Using with
 * GlobeView").
 *
 * No hace: no mueve la cámara (eso es `labScript.ts`).
 */
import type { Layer } from '@deck.gl/core';
import { PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import { MapLibreOverlay } from '@deck.gl/maplibre';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { arcPath, KIND_COLOR, type LabCase, LEGAL_COLOR, nodesById } from './labCase';
import { addNodeLabels, type MuroEngine, removeNodeSource } from './muroLabels';

// Igual que la opción A, para comparar lo mismo.
const ARC_SAMPLES = 48;
const RIBBON_WIDTH_PX = 14;
const CORE_WIDTH_PX = 2.5;
const PULSE_SPEED = 0.22;

type Rgb = [number, number, number];
type Rgba = [number, number, number, number];

function hexToRgb(hex: string): Rgb {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

interface ArcDatum {
  path: [number, number, number][];
  color: Rgb;
  confidence: number;
  confirmed: boolean;
  phase: number;
}

interface NodeDatum {
  position: [number, number];
  color: Rgb;
  ring: Rgb;
}

const CONFIRMED: Rgb = [125, 211, 252];
const SUGGESTED: Rgb = [203, 213, 225];
// Mezcla aditiva y sin descarte de caras (globo), como en la opción A.
const GLOW_PARAMETERS = {
  cullMode: 'none',
  depthCompare: 'always',
  depthWriteEnabled: false,
  blend: true,
  blendColorSrcFactor: 'src-alpha',
  blendColorDstFactor: 'one',
  blendAlphaSrcFactor: 'one',
  blendAlphaDstFactor: 'one',
} as const;

/** Punto del arco en la fracción `t` (0..1) de su recorrido. */
function pointAt(path: readonly [number, number, number][], t: number): [number, number, number] {
  const last = path.length - 1;
  const exact = t * last;
  const i = Math.min(last - 1, Math.floor(exact));
  const a = path[i] ?? path[0] ?? [0, 0, 0];
  const b = path[i + 1] ?? a;
  const f = exact - i;
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

function buildLayers(arcs: ArcDatum[], nodes: NodeDatum[], seconds: number): Layer[] {
  const alpha = (d: ArcDatum, base: number): number =>
    Math.round(base * (d.confirmed ? 0.45 + 0.55 * d.confidence : 0.35));
  const comets = arcs.map((d) => pointAt(d.path, (seconds * PULSE_SPEED + d.phase) % 1));
  const haloRadius = 14 + 5 * Math.sin((seconds * 1000) / 450);
  return [
    new PathLayer<ArcDatum>({
      id: 'muro-arc-halo',
      data: arcs,
      getPath: (d) => d.path,
      getColor: (d): Rgba => [...d.color, alpha(d, 70)],
      getWidth: RIBBON_WIDTH_PX,
      widthUnits: 'pixels',
      parameters: GLOW_PARAMETERS,
    }),
    new PathLayer<ArcDatum>({
      id: 'muro-arc-core',
      data: arcs,
      getPath: (d) => d.path,
      getColor: (d): Rgba => [...d.color, alpha(d, 255)],
      getWidth: CORE_WIDTH_PX,
      widthUnits: 'pixels',
      parameters: GLOW_PARAMETERS,
    }),
    new ScatterplotLayer<[number, number, number]>({
      id: 'muro-comets',
      data: comets,
      getPosition: (d) => d,
      getRadius: 4,
      radiusUnits: 'pixels',
      getFillColor: [255, 255, 255, 230],
      parameters: GLOW_PARAMETERS,
    }),
    new ScatterplotLayer<NodeDatum>({
      id: 'muro-node-halo',
      data: nodes,
      getPosition: (d) => d.position,
      getRadius: haloRadius,
      radiusUnits: 'pixels',
      getFillColor: (d): Rgba => [...d.color, 90],
      updateTriggers: { getRadius: haloRadius },
      parameters: GLOW_PARAMETERS,
    }),
    new ScatterplotLayer<NodeDatum>({
      id: 'muro-node-core',
      data: nodes,
      getPosition: (d) => d.position,
      getRadius: 5.5,
      radiusUnits: 'pixels',
      stroked: true,
      getFillColor: (d) => d.color,
      getLineColor: (d) => d.ring,
      getLineWidth: 2,
      lineWidthUnits: 'pixels',
      parameters: { cullMode: 'none' },
    }),
  ];
}

/**
 * Dibuja el caso con la opción B.
 *
 * @param map Mapa ya cargado.
 * @param labCase Caso a dibujar.
 * @returns Cómo quitarlo.
 */
export function addDeckMuro(map: MapLibreMap, labCase: LabCase): MuroEngine {
  addNodeLabels(map, labCase);
  const byId = nodesById(labCase);
  const arcs: ArcDatum[] = [];
  labCase.links.forEach((link, index) => {
    const a = byId.get(link.from);
    const b = byId.get(link.to);
    if (!a || !b) return;
    arcs.push({
      path: arcPath([a.lng, a.lat], [b.lng, b.lat], ARC_SAMPLES),
      color: link.confirmed ? CONFIRMED : SUGGESTED,
      confidence: link.confidence,
      confirmed: link.confirmed,
      phase: (index * 0.618) % 1,
    });
  });
  const nodes: NodeDatum[] = labCase.nodes.map((node) => ({
    position: [node.lng, node.lat],
    color: hexToRgb(KIND_COLOR[node.kind]),
    ring: hexToRgb(node.legal ? LEGAL_COLOR[node.legal] : '#E2E8F0'),
  }));
  const overlay = new MapLibreOverlay({ interleaved: true, layers: [] });
  map.addControl(overlay);
  let frame = 0;
  const animate = (now: number) => {
    frame = requestAnimationFrame(animate);
    overlay.setProps({ layers: buildLayers(arcs, nodes, now / 1000) });
  };
  frame = requestAnimationFrame(animate);
  return {
    remove: () => {
      cancelAnimationFrame(frame);
      map.removeControl(overlay);
      removeNodeSource(map, []);
    },
  };
}
