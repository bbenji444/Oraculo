/**
 * Nodos del muro como datos de MapLibre: la fuente GeoJSON y las etiquetas
 * (Fases 9.1 y 9.6).
 *
 * Las etiquetas van con MapLibre (texto nítido con las fuentes del mapa, que
 * ya traen la Ñ).
 *
 * No hace: no dibuja los círculos ni los arcos (eso es `engine.ts`).
 */
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';

import type { WallCase } from './types';

export const MURO_SOURCE = 'muro-nodes';
export const MURO_LABELS_LAYER = 'muro-node-labels';
// Las etiquetas aparecen desde el zoom de una ciudad: más lejos, con muchos
// nodos, solo estorban (la 9.1 las ponía desde 5 con nodos en varias ciudades;
// en un caso real todo cae en una alcaldía).
const LABELS_MIN_ZOOM = 9;
const LABEL_FONT = ['Noto Sans Regular'];

/** Nodos como GeoJSON (tipo propio, como `NewsFeatureCollection` de las noticias). */
export interface NodeFeatureCollection {
  type: 'FeatureCollection';
  features: {
    type: 'Feature';
    id: string;
    geometry: { type: 'Point'; coordinates: [number, number] };
    properties: {
      nodeId: string;
      label: string;
      color: string;
      ring: string;
      focus: number;
      selected: boolean;
    };
  }[];
}

/** GeoJSON de los nodos, con su color de tipo, de estatus legal y su realce. */
export function nodesGeoJson(wall: WallCase): NodeFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: wall.nodes.map((node) => ({
      type: 'Feature',
      id: node.id,
      geometry: { type: 'Point', coordinates: [node.lng, node.lat] },
      properties: {
        nodeId: node.id,
        label: node.label,
        color: node.color,
        ring: node.ring,
        focus: node.focus,
        selected: node.selected,
      },
    })),
  };
}

/** Agrega la fuente de nodos y sus etiquetas. */
export function addNodeLabels(map: MapLibreMap, wall: WallCase): void {
  map.addSource(MURO_SOURCE, { type: 'geojson', data: nodesGeoJson(wall) });
  map.addLayer({
    id: MURO_LABELS_LAYER,
    type: 'symbol',
    source: MURO_SOURCE,
    minzoom: LABELS_MIN_ZOOM,
    layout: {
      'text-field': ['get', 'label'],
      'text-font': LABEL_FONT,
      'text-size': ['case', ['get', 'selected'], 14, 12],
      'text-offset': [0, 1.5],
      'text-anchor': 'top',
      'text-optional': true,
      'text-max-width': 12,
    },
    paint: {
      'text-color': '#E2E8F0',
      'text-opacity': ['get', 'focus'],
      'text-halo-color': '#020617',
      'text-halo-width': 1.4,
    },
  });
}

/** Cambia los datos de los nodos sin quitar las capas. */
export function setNodeData(map: MapLibreMap, wall: WallCase): void {
  const source = map.getSource<GeoJSONSource>(MURO_SOURCE);
  // setData responde cuando el mapa ya procesó los datos; aquí no hay que esperarlo.
  void source?.setData(nodesGeoJson(wall));
}

/** Lo que devuelve el motor, para actualizarlo o quitarlo. */
export interface MuroEngine {
  /** Redibuja con otros datos (otro realce, otra vista) sin recrear las capas. */
  update: (wall: WallCase) => void;
  remove: () => void;
}

/** Quita lo que agregó `addNodeLabels` (y las capas que usen su fuente). */
export function removeNodeSource(map: MapLibreMap, layerIds: readonly string[]): void {
  for (const id of [...layerIds, MURO_LABELS_LAYER]) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  if (map.getSource(MURO_SOURCE)) map.removeSource(MURO_SOURCE);
}
