/**
 * Nodos del muro como datos de MapLibre: la fuente GeoJSON y las etiquetas.
 *
 * Las etiquetas van con MapLibre (texto nítido con las fuentes del mapa, que
 * ya traen la Ñ). Al comparar motores en el ADR-0102 las dos opciones las
 * compartían, así los fps medían solo el dibujo de nodos y arcos.
 *
 * No hace: no dibuja los círculos ni los arcos (eso es `muroMapLibre.ts`).
 */
import type { Map as MapLibreMap } from 'maplibre-gl';

import { KIND_COLOR, type LabCase, LEGAL_COLOR } from './labCase';

export const MURO_SOURCE = 'muro-nodes';
export const MURO_LABELS_LAYER = 'muro-node-labels';
// Las etiquetas aparecen desde el zoom de un estado: en la vista de país, con
// 150 nodos, solo estorban.
const LABELS_MIN_ZOOM = 5;
const LABEL_FONT = ['Noto Sans Regular'];

/** Nodos como GeoJSON (tipo propio, como `NewsFeatureCollection` de las noticias). */
export interface NodeFeatureCollection {
  type: 'FeatureCollection';
  features: {
    type: 'Feature';
    id: string;
    geometry: { type: 'Point'; coordinates: [number, number] };
    properties: { label: string; color: string; ring: string };
  }[];
}

/** GeoJSON de los nodos, con su color de tipo y de estatus legal. */
export function nodesGeoJson(labCase: LabCase): NodeFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: labCase.nodes.map((node) => ({
      type: 'Feature',
      id: node.id,
      geometry: { type: 'Point', coordinates: [node.lng, node.lat] },
      properties: {
        label: node.label,
        color: KIND_COLOR[node.kind],
        ring: node.legal ? LEGAL_COLOR[node.legal] : '#E2E8F0',
      },
    })),
  };
}

/** Agrega la fuente de nodos y sus etiquetas. */
export function addNodeLabels(map: MapLibreMap, labCase: LabCase): void {
  map.addSource(MURO_SOURCE, { type: 'geojson', data: nodesGeoJson(labCase) });
  map.addLayer({
    id: MURO_LABELS_LAYER,
    type: 'symbol',
    source: MURO_SOURCE,
    minzoom: LABELS_MIN_ZOOM,
    layout: {
      'text-field': ['get', 'label'],
      'text-font': LABEL_FONT,
      'text-size': 12,
      'text-offset': [0, 1.5],
      'text-anchor': 'top',
      'text-optional': true,
    },
    paint: {
      'text-color': '#E2E8F0',
      'text-halo-color': '#020617',
      'text-halo-width': 1.4,
    },
  });
}

/** Lo que devuelve cada opción del muro, para poder quitarla al cambiar de opción. */
export interface MuroEngine {
  remove: () => void;
}

/** Quita lo que agregó `addNodeLabels` (y las capas que usen su fuente). */
export function removeNodeSource(map: MapLibreMap, layerIds: readonly string[]): void {
  for (const id of [...layerIds, MURO_LABELS_LAYER]) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  if (map.getSource(MURO_SOURCE)) map.removeSource(MURO_SOURCE);
}
