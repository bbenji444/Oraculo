/**
 * Construye el estilo de MapLibre del globo: mapa base de Protomaps (en
 * español; variante oscura de noche y clara de día) y las capas de INEGI encima.
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
// Los polígonos del mapa mundial siguen 2 niveles más debajo del de México.
// MapLibre filtra las capas por el zoom de cada tesela: con la cámara
// inclinada, las teselas lejanas son de un zoom menor y, justo en el cambio,
// quedaba un hueco sin ninguno de los dos mapas (visto el 17/10/2026). Las
// etiquetas no se traslapan para no duplicarse.
export const WORLD_POLYGON_OVERLAP_ZOOMS = 2;

/** Atribución obligatoria (ADR-0008). */
export const ATTRIBUTION_INEGI = '© INEGI · Natural Earth';
/** Crédito de las texturas de la Tierra (ADR-0017). */
export const ATTRIBUTION_NASA = 'Imágenes: NASA Earth Observatory · NASA SVS';

/** Cara de la Tierra: de noche con luces (por defecto) o de día. */
export type EarthMode = 'night' | 'day';

/** Id de la capa de textura de cada cara. */
export const EARTH_LAYER: Record<EarthMode, string> = { night: 'earth-night', day: 'earth-day' };

// La textura de la NASA cubre el globo hasta el zoom 5 y se desvanece hasta el
// 7, donde ya manda el mapa de calles (su resolución, ~2 km/píxel, no da más).
export const EARTH_FADE_START_ZOOM = 5;
export const EARTH_FADE_END_ZOOM = 7;
// Las etiquetas del mapa base aparecen desde aquí: en la vista de globo no
// ensucian la Tierra (como en las imágenes de referencia de Benji).
export const LABELS_MIN_ZOOM = 3.5;
// Fuerza del halo atmosférico de MapLibre (`atmosphere-blend`, 0 a 1): con 1
// el borde del globo se veía demasiado azul (Benji, 26/10/2026).
export const ATMOSPHERE_STRENGTH = 0.6;
export const ATTRIBUTION_OSM =
  '© <a href="https://openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">colaboradores de OpenStreetMap</a> · <a href="https://protomaps.com" target="_blank" rel="noopener noreferrer">Protomaps</a>';

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
        // Tenues sobre la textura de la NASA en la vista de globo; más marcadas al
        // acercarse, cuando ya se ve el mapa de calles.
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 1, 0.22, 5, 0.55],
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

/** Variante de colores del mapa de calles de Protomaps. */
export type BasemapFlavor = 'light' | 'dark';

/**
 * Variante del mapa de calles que acompaña a cada cara de la Tierra.
 *
 * Al acercarse, la textura de la NASA se funde con el mapa de calles: con la
 * Tierra de día, un mapa oscuro hacía parecer que era de noche (lo notó Benji
 * el 20/10/2026).
 *
 * @param earth Cara de la Tierra visible.
 * @returns `light` de día y `dark` de noche.
 */
export function basemapFlavor(earth: EarthMode): BasemapFlavor {
  return earth === 'day' ? 'light' : 'dark';
}

/** Copia las capas del mapa base apuntando a una fuente y un rango de zoom. */
function basemapFor(
  source: 'basemap_world' | 'basemap_mexico',
  range: { minzoom?: number; maxzoom?: number },
  flavor: BasemapFlavor,
): LayerSpecification[] {
  const all = basemapLayers(source, namedFlavor(flavor), { lang: 'es' });
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

function earthSource(origin: string, mode: EarthMode): SourceSpecification {
  return {
    type: 'raster',
    url: `pmtiles://${origin}/tiles/earth_${mode}.pmtiles`,
    tileSize: 256,
    attribution: ATTRIBUTION_NASA,
  };
}

/** Ajustes de color de cada cara de la Tierra (medidos a ojo en el globo, 26/10/2026). */
const EARTH_LOOK: Record<EarthMode, Record<string, number>> = {
  day: { 'raster-saturation': 0.18, 'raster-contrast': 0.12, 'raster-brightness-min': 0.02 },
  night: { 'raster-saturation': 0.25, 'raster-contrast': 0.22, 'raster-brightness-max': 1 },
};

function earthLayer(mode: EarthMode, visible: boolean): LayerSpecification {
  return {
    id: EARTH_LAYER[mode],
    type: 'raster',
    source: `earth_${mode}`,
    maxzoom: EARTH_FADE_END_ZOOM,
    layout: { visibility: visible ? 'visible' : 'none' },
    paint: {
      'raster-opacity': [
        'interpolate',
        ['linear'],
        ['zoom'],
        EARTH_FADE_START_ZOOM,
        1,
        EARTH_FADE_END_ZOOM,
        0,
      ],
      // Interpolación suave entre píxeles: sin escalones al acercarse.
      'raster-resampling': 'linear',
      // Más vida a las imágenes de la NASA (26/10/2026): de día, un poco más
      // de color y contraste; de noche, las luces de las ciudades resaltan.
      // La iluminación sigue pareja: el día y la noche los elige el analista.
      ...EARTH_LOOK[mode],
      // Sin parpadeo al llegar teselas nuevas mientras gira.
      'raster-fade-duration': 0,
    },
  };
}

/**
 * Arma el estilo completo del globo.
 *
 * Orden de abajo arriba: polígonos del mapa base mundial, la textura de la
 * NASA (que los tapa en la vista de globo y se desvanece al acercarse), el
 * detalle de México, las capas de INEGI y, al final, las etiquetas.
 *
 * @param origin Origen del sitio (por ejemplo `http://localhost:8080`); las
 *   teselas, fuentes y sprite se piden al mismo origen, nunca a terceros.
 * @param earth Cara de la Tierra visible; también decide si el mapa de calles
 *   es claro (día) u oscuro (noche).
 * @returns El estilo listo para `new maplibregl.Map({ style })`.
 */
export function buildMapStyle(origin: string, earth: EarthMode = 'night'): StyleSpecification {
  const assets = `${origin}/tiles/basemap-assets`;
  const flavor = basemapFlavor(earth);
  const background = basemapLayers('basemap_world', namedFlavor(flavor), { lang: 'es' }).find(
    (layer) => layer.type === 'background',
  ) as LayerSpecification | undefined;
  const world = basemapFor('basemap_world', { maxzoom: BASEMAP_SWITCH_ZOOM }, flavor);
  const worldPolygons = basemapFor(
    'basemap_world',
    { maxzoom: BASEMAP_SWITCH_ZOOM + WORLD_POLYGON_OVERLAP_ZOOMS },
    flavor,
  );
  const mexico = basemapFor('basemap_mexico', { minzoom: BASEMAP_SWITCH_ZOOM }, flavor);
  return {
    version: 8,
    projection: { type: 'globe' },
    // Halo atmosférico alrededor del globo, que se desvanece al acercarse. Al
    // 60 %: completo se veía demasiado azul (Benji, 26/10/2026).
    sky: {
      'atmosphere-blend': [
        'interpolate',
        ['linear'],
        ['zoom'],
        0,
        ATMOSPHERE_STRENGTH,
        5,
        ATMOSPHERE_STRENGTH,
        7,
        0,
      ],
    },
    glyphs: `${assets}/fonts/{fontstack}/{range}.pbf`,
    sprite: `${assets}/sprites/v4/${flavor}`,
    sources: {
      basemap_world: pmtilesSource(origin, 'basemap_world.pmtiles', ATTRIBUTION_OSM),
      basemap_mexico: pmtilesSource(origin, 'basemap_mexico.pmtiles', ATTRIBUTION_OSM),
      earth_night: earthSource(origin, 'night'),
      earth_day: earthSource(origin, 'day'),
      countries: pmtilesSource(origin, 'countries.pmtiles', ATTRIBUTION_INEGI),
      states: pmtilesSource(origin, 'states.pmtiles', ATTRIBUTION_INEGI),
      municipalities: pmtilesSource(origin, 'municipalities.pmtiles', ATTRIBUTION_INEGI),
      localities: pmtilesSource(origin, 'localities.pmtiles', ATTRIBUTION_INEGI),
    },
    layers: [
      ...(background ? [{ ...background, id: 'background' }] : []),
      ...worldPolygons.filter((layer) => layer.type !== 'symbol'),
      earthLayer('day', earth === 'day'),
      earthLayer('night', earth === 'night'),
      ...mexico.filter((layer) => layer.type !== 'symbol'),
      ...regionLayers(),
      ...world
        .filter((layer) => layer.type === 'symbol')
        .map((layer) => ({ ...layer, minzoom: Math.max(layer.minzoom ?? 0, LABELS_MIN_ZOOM) })),
      ...mexico.filter((layer) => layer.type === 'symbol'),
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

/**
 * Zoom máximo al volar a una región, para no acercarse de más a un estado.
 * Países hasta 6 (el último zoom del mapa base del mundo): con 4, los chicos
 * como Países Bajos o El Salvador quedaban lejos.
 */
export const FLY_MAX_ZOOM: Record<RegionLevel, number> = {
  country: 6,
  // Más cerca desde el 26/10/2026 (Benji: acercarse al lugar de los hechos).
  state: 8,
  municipality: 12.5,
  locality: 15,
};
