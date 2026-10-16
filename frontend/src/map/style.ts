/**
 * Construye el estilo de MapLibre del globo: mapa base de Protomaps (en
 * español, variante oscura) y las capas de INEGI encima.
 *
 * Es una función pura (no toca el DOM ni la red) para poder probarla.
 *
 * Mapa base en dos archivos (ADR-0004, geodata/README.md):
 * - `basemap_world` (mundo hasta zoom 6) se dibuja por debajo de BASEMAP_SWITCH_ZOOM;
 * - `basemap_mexico` (México hasta zoom 14) se dibuja desde ese zoom.
 * Así no se duplican calles ni etiquetas donde los dos archivos se traslapan.
 * Fuera de México, al acercarse, solo quedan los contornos de países: el
 * detalle interno existe solo para México en esta versión (especificación H4).
 */
import { layers as basemapLayers, namedFlavor } from '@protomaps/basemaps';
import type {
  ExpressionSpecification,
  LayerSpecification,
  SourceSpecification,
  StyleSpecification,
} from 'maplibre-gl';

/** Zoom a partir del cual se usa el mapa base detallado de México. */
export const BASEMAP_SWITCH_ZOOM = 7;

/** Atribución obligatoria (ADR-0008). */
export const ATTRIBUTION_INEGI = '© INEGI · Natural Earth';
export const ATTRIBUTION_OSM =
  '© <a href="https://openstreetmap.org/copyright">colaboradores de OpenStreetMap</a> · <a href="https://protomaps.com">Protomaps</a>';

export type RegionLevel = 'country' | 'state' | 'municipality' | 'locality';

/** Fuente de teselas de cada nivel; el nombre de capa interna es el mismo. */
export const SOURCE_BY_LEVEL: Record<RegionLevel, string> = {
  country: 'countries',
  state: 'states',
  municipality: 'municipalities',
  locality: 'localities',
};

/** Capas sobre las que reacciona el cursor, de la más específica a la más general. */
export const INTERACTIVE_LAYERS = [
  'localities-point',
  'municipalities-fill',
  'states-fill',
  'countries-fill',
];

const COLORS = {
  country: '#94a3b8',
  state: '#38bdf8',
  municipality: '#a78bfa',
  locality: '#fbbf24',
  outline: '#0f172a',
};

/** Expresión: verdadero si la figura está bajo el cursor o seleccionada. */
function stateOn(name: 'hover' | 'selected'): ExpressionSpecification {
  return ['boolean', ['feature-state', name], false];
}

function fillOpacity(hover: number, selected: number): ExpressionSpecification {
  return ['case', stateOn('selected'), selected, stateOn('hover'), hover, 0];
}

function regionLayers(): LayerSpecification[] {
  return [
    {
      id: 'countries-fill',
      type: 'fill',
      source: 'countries',
      'source-layer': 'countries',
      paint: { 'fill-color': COLORS.country, 'fill-opacity': fillOpacity(0.12, 0.2) },
    },
    {
      id: 'countries-line',
      type: 'line',
      source: 'countries',
      'source-layer': 'countries',
      paint: {
        'line-color': COLORS.country,
        'line-opacity': 0.55,
        'line-width': ['interpolate', ['linear'], ['zoom'], 0, 0.4, 6, 1.2],
      },
    },
    {
      id: 'states-fill',
      type: 'fill',
      source: 'states',
      'source-layer': 'states',
      minzoom: 2,
      paint: { 'fill-color': COLORS.state, 'fill-opacity': fillOpacity(0.14, 0.22) },
    },
    {
      id: 'states-line',
      type: 'line',
      source: 'states',
      'source-layer': 'states',
      minzoom: 2,
      paint: {
        'line-color': COLORS.state,
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 2, 0.5, 8, 0.85],
        // El zoom debe ir en el nivel superior de la expresión (regla de
        // MapLibre); la selección se decide dentro de cada parada.
        'line-width': [
          'interpolate',
          ['linear'],
          ['zoom'],
          2,
          ['case', stateOn('selected'), 2.5, 0.6],
          10,
          ['case', stateOn('selected'), 4, 2],
        ],
      },
    },
    {
      id: 'municipalities-fill',
      type: 'fill',
      source: 'municipalities',
      'source-layer': 'municipalities',
      minzoom: 5,
      paint: { 'fill-color': COLORS.municipality, 'fill-opacity': fillOpacity(0.18, 0.26) },
    },
    {
      id: 'municipalities-line',
      type: 'line',
      source: 'municipalities',
      'source-layer': 'municipalities',
      minzoom: 5,
      paint: {
        'line-color': COLORS.municipality,
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.25, 9, 0.7],
        'line-width': [
          'interpolate',
          ['linear'],
          ['zoom'],
          5,
          ['case', stateOn('selected'), 2, 0.3],
          14,
          ['case', stateOn('selected'), 3.5, 1.4],
        ],
      },
    },
    {
      id: 'localities-point',
      type: 'circle',
      source: 'localities',
      'source-layer': 'localities',
      minzoom: 10,
      paint: {
        'circle-color': COLORS.locality,
        'circle-radius': [
          'interpolate',
          ['linear'],
          ['zoom'],
          10,
          ['case', stateOn('selected'), 6, stateOn('hover'), 5, 2],
          14,
          ['case', stateOn('selected'), 8, stateOn('hover'), 7, 4.5],
        ],
        'circle-stroke-color': COLORS.outline,
        'circle-stroke-width': 1,
        'circle-opacity': 0.9,
      },
    },
  ];
}

/** Copia las capas del mapa base apuntando a una fuente y un rango de zoom. */
function basemapFor(
  source: 'basemap_world' | 'basemap_mexico',
  range: { minzoom?: number; maxzoom?: number },
): LayerSpecification[] {
  const all = basemapLayers(source, namedFlavor('dark'), { lang: 'es' });
  return all
    .filter((layer) => layer.type !== 'background')
    .map((layer) => ({
      ...layer,
      id: `${source}-${layer.id}`,
      minzoom: Math.max(layer.minzoom ?? 0, range.minzoom ?? 0),
      maxzoom: Math.min(layer.maxzoom ?? 24, range.maxzoom ?? 24),
    }));
}

function pmtilesSource(origin: string, file: string, attribution: string): SourceSpecification {
  return { type: 'vector', url: `pmtiles://${origin}/tiles/${file}`, attribution };
}

/**
 * Arma el estilo completo del globo.
 *
 * @param origin Origen del sitio (por ejemplo `http://localhost:8080`); las
 *   teselas, fuentes y sprite se piden al mismo origen, nunca a terceros.
 * @returns El estilo listo para `new maplibregl.Map({ style })`.
 */
export function buildMapStyle(origin: string): StyleSpecification {
  const assets = `${origin}/tiles/basemap-assets`;
  const background = basemapLayers('basemap_world', namedFlavor('dark'), { lang: 'es' }).find(
    (layer) => layer.type === 'background',
  ) as LayerSpecification | undefined;
  return {
    version: 8,
    projection: { type: 'globe' },
    // Halo atmosférico alrededor del globo, que se desvanece al acercarse.
    sky: { 'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0] },
    glyphs: `${assets}/fonts/{fontstack}/{range}.pbf`,
    sprite: `${assets}/sprites/v4/dark`,
    sources: {
      basemap_world: pmtilesSource(origin, 'basemap_world.pmtiles', ATTRIBUTION_OSM),
      basemap_mexico: pmtilesSource(origin, 'basemap_mexico.pmtiles', ATTRIBUTION_OSM),
      countries: pmtilesSource(origin, 'countries.pmtiles', ATTRIBUTION_INEGI),
      states: pmtilesSource(origin, 'states.pmtiles', ATTRIBUTION_INEGI),
      municipalities: pmtilesSource(origin, 'municipalities.pmtiles', ATTRIBUTION_INEGI),
      localities: pmtilesSource(origin, 'localities.pmtiles', ATTRIBUTION_INEGI),
    },
    layers: [
      ...(background ? [{ ...background, id: 'background' }] : []),
      ...basemapFor('basemap_world', { maxzoom: BASEMAP_SWITCH_ZOOM }),
      ...basemapFor('basemap_mexico', { minzoom: BASEMAP_SWITCH_ZOOM }),
      ...regionLayers(),
    ],
  };
}

/** Propiedades que trae cada figura de las teselas de INEGI (geodata/README.md). */
export interface RegionFeatureProps {
  code?: unknown;
  name?: unknown;
  display_prefix?: unknown;
  level?: unknown;
}

/**
 * Texto del tooltip de una figura: "Alcaldía Iztapalapa", "Jalisco".
 *
 * Igual que `display_name` de la API: municipios y localidades con su
 * prefijo; países y estados solo con su nombre.
 *
 * @param props Propiedades de la figura.
 * @returns El texto, o `null` si la figura no trae nombre.
 */
export function featureLabel(props: RegionFeatureProps): string | null {
  if (typeof props.name !== 'string' || props.name === '') return null;
  const withPrefix = props.level === 'municipality' || props.level === 'locality';
  return withPrefix && typeof props.display_prefix === 'string'
    ? `${props.display_prefix} ${props.name}`
    : props.name;
}

/** Zoom máximo al volar a una región, para no acercarse de más a un estado. */
export const FLY_MAX_ZOOM: Record<RegionLevel, number> = {
  country: 4,
  state: 7,
  municipality: 11,
  locality: 14,
};
