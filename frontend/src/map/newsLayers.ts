/**
 * Las notas de una búsqueda sobre el globo (especificación §14.2 "Resultados en
 * el mapa"; ADR-0017):
 *
 * - mapa de calor al alejarse;
 * - grupos de puntos (clusters) con su número;
 * - cada nota como un punto con brillo, del color de su concepto, que aparece
 *   en cascada y late al elegirla;
 * - las ubicadas solo por estado o país se dibujan con un **anillo punteado**
 *   en el centro de la región, para no hacer creer que pasaron ahí exactamente.
 *
 * Funciones puras (sin mapa ni DOM): datos GeoJSON y estilos de las capas.
 */
import type { ExpressionSpecification, LayerSpecification } from 'maplibre-gl';

import type { Article } from '../services/searches';

export const NEWS_SOURCE = 'news';
// Imagen del anillo punteado (se crea al cargar el mapa).
export const DASHED_RING_IMAGE = 'news-ring-dashed';
// Color por defecto de una nota sin concepto relevante.
export const NEWS_DEFAULT_COLOR = '#38BDF8';
// Grupos: se juntan puntos a menos de 42 px y se separan desde el zoom 9.
export const CLUSTER_RADIUS_PX = 42;
export const CLUSTER_MAX_ZOOM = 9;
// El mapa de calor se ve de lejos y se apaga al acercarse, donde ya se
// distinguen los puntos.
export const HEAT_MAX_ZOOM = 6;

/** Propiedades de cada punto (lo que leen las capas y el clic). */
export interface NewsPointProps {
  id: number;
  color: string;
  coarse: boolean;
  inRegion: 'true' | 'false' | 'none';
}

export interface NewsFeatureCollection {
  type: 'FeatureCollection';
  features: {
    type: 'Feature';
    id: number;
    geometry: { type: 'Point'; coordinates: [number, number] };
    properties: NewsPointProps;
  }[];
}

/**
 * Puntos GeoJSON de las notas con ubicación (las demás van a "Sin ubicación").
 *
 * @param articles Notas de la búsqueda.
 * @param colors Color de cada concepto.
 */
export function newsFeatures(
  articles: readonly Article[],
  colors: ReadonlyMap<number, string>,
): NewsFeatureCollection {
  const features: NewsFeatureCollection['features'] = [];
  for (const article of articles) {
    const location = article.primary_location;
    const lon = location?.lon ?? null;
    const lat = location?.lat ?? null;
    if (location === null || lon === null || lat === null) continue;
    const firstRelevant = article.concepts.find((c) => c.is_relevant);
    features.push({
      type: 'Feature',
      id: article.article_id,
      geometry: { type: 'Point', coordinates: [lon, lat] },
      properties: {
        id: article.article_id,
        color:
          (firstRelevant === undefined ? undefined : colors.get(firstRelevant.concept_id)) ??
          NEWS_DEFAULT_COLOR,
        coarse: location.precision === 'country' || location.precision === 'state',
        inRegion: article.in_region === null ? 'none' : article.in_region ? 'true' : 'false',
      },
    });
  }
  return { type: 'FeatureCollection', features };
}

const UNCLUSTERED: ExpressionSpecification = ['!', ['has', 'point_count']];
const PRECISE: ExpressionSpecification = ['all', UNCLUSTERED, ['!', ['get', 'coarse']]];
const COARSE: ExpressionSpecification = ['all', UNCLUSTERED, ['get', 'coarse']];
// Aparición en cascada: el punto se enciende cuando su estado "shown" es true.
const SHOWN: ExpressionSpecification = ['boolean', ['feature-state', 'shown'], false];
const HOVER: ExpressionSpecification = ['boolean', ['feature-state', 'hover'], false];

/** Filtro de la capa de latido: solo la nota elegida. */
export function selectedFilter(articleId: number | null): ExpressionSpecification {
  return ['all', UNCLUSTERED, ['==', ['get', 'id'], articleId ?? -1]];
}

/** Capas de las notas, de abajo arriba. */
export function newsLayers(): LayerSpecification[] {
  return [
    {
      id: 'news-heat',
      type: 'heatmap',
      source: NEWS_SOURCE,
      maxzoom: HEAT_MAX_ZOOM,
      paint: {
        'heatmap-weight': ['coalesce', ['get', 'point_count'], 1],
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 0.6, HEAT_MAX_ZOOM, 1.4],
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 14, HEAT_MAX_ZOOM, 36],
        'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 3, 0.75, HEAT_MAX_ZOOM, 0],
        // Del azul frío al ámbar: se lee sobre la Tierra de noche.
        'heatmap-color': [
          'interpolate',
          ['linear'],
          ['heatmap-density'],
          0,
          'rgba(14,165,233,0)',
          0.3,
          'rgba(56,189,248,0.55)',
          0.6,
          'rgba(250,204,21,0.75)',
          1,
          'rgba(251,113,133,0.9)',
        ],
      },
    },
    {
      id: 'news-cluster',
      type: 'circle',
      source: NEWS_SOURCE,
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': 'rgba(56,189,248,0.25)',
        'circle-stroke-color': 'rgba(186,230,253,0.9)',
        'circle-stroke-width': 1.5,
        'circle-radius': ['step', ['get', 'point_count'], 14, 5, 18, 20, 24],
        'circle-blur': 0.15,
      },
    },
    {
      id: 'news-cluster-count',
      type: 'symbol',
      source: NEWS_SOURCE,
      filter: ['has', 'point_count'],
      layout: {
        'text-field': ['get', 'point_count_abbreviated'],
        'text-font': ['Noto Sans Medium'],
        'text-size': 12,
      },
      paint: { 'text-color': '#E0F2FE' },
    },
    {
      // Halo de luz alrededor de cada punto preciso.
      id: 'news-glow',
      type: 'circle',
      source: NEWS_SOURCE,
      filter: PRECISE,
      paint: {
        'circle-color': ['get', 'color'],
        'circle-radius': ['case', HOVER, 18, 13],
        'circle-blur': 1,
        'circle-opacity': ['case', SHOWN, 0.55, 0],
        'circle-opacity-transition': { duration: 450 },
        'circle-radius-transition': { duration: 150 },
      },
    },
    {
      id: 'news-point',
      type: 'circle',
      source: NEWS_SOURCE,
      filter: PRECISE,
      paint: {
        'circle-color': ['get', 'color'],
        'circle-radius': ['case', HOVER, 6.5, 5],
        'circle-stroke-color': '#F8FAFC',
        'circle-stroke-width': 1.2,
        'circle-opacity': ['case', SHOWN, 1, 0],
        'circle-stroke-opacity': ['case', SHOWN, 0.9, 0],
        'circle-opacity-transition': { duration: 450 },
        'circle-radius-transition': { duration: 150 },
      },
    },
    {
      // Ubicadas solo por estado o país: anillo punteado (§14.2).
      id: 'news-coarse',
      type: 'symbol',
      source: NEWS_SOURCE,
      filter: COARSE,
      layout: {
        'icon-image': DASHED_RING_IMAGE,
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
      },
      paint: {
        'icon-opacity': ['case', SHOWN, 0.95, 0],
        'icon-opacity-transition': { duration: 450 },
      },
    },
    {
      // Latido de la nota elegida (radio y opacidad se animan cuadro a cuadro).
      id: 'news-pulse',
      type: 'circle',
      source: NEWS_SOURCE,
      filter: selectedFilter(null),
      paint: {
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-color': '#F8FAFC',
        'circle-stroke-width': 2,
        'circle-radius': 8,
        'circle-stroke-opacity': 1,
      },
    },
  ];
}

// El latido crece de 8 a 30 px y se desvanece.
export const PULSE_MIN_RADIUS = 8;
export const PULSE_MAX_RADIUS = 30;

/** Radio y opacidad del latido en una fase (0 a 1). */
export function pulseStyle(phase: number): { radius: number; opacity: number } {
  return {
    radius: PULSE_MIN_RADIUS + (PULSE_MAX_RADIUS - PULSE_MIN_RADIUS) * phase,
    opacity: 1 - phase,
  };
}

/**
 * Dice si un punto está del lado visible del globo (para ocultar su ficha).
 *
 * @param center Centro de la vista.
 * @param point Punto.
 * @param margin Grados antes del borde en que ya se oculta.
 */
export function isOnVisibleSide(
  center: { lng: number; lat: number },
  point: { lng: number; lat: number },
  margin = 8,
): boolean {
  const toRad = Math.PI / 180;
  const cos =
    Math.sin(center.lat * toRad) * Math.sin(point.lat * toRad) +
    Math.cos(center.lat * toRad) *
      Math.cos(point.lat * toRad) *
      Math.cos((point.lng - center.lng) * toRad);
  return Math.acos(Math.min(1, Math.max(-1, cos))) / toRad < 90 - margin;
}

/**
 * Píxeles RGBA de un anillo punteado (para `map.addImage`).
 *
 * @param size Lado de la imagen en píxeles.
 * @param dashes Cuántos trazos tiene el anillo.
 */
export function dashedRingPixels(size = 44, dashes = 12): Uint8Array {
  const pixels = new Uint8Array(size * size * 4);
  const center = (size - 1) / 2;
  const outer = size / 2 - 2;
  const inner = outer - 3;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = x - center;
      const dy = y - center;
      const distance = Math.hypot(dx, dy);
      if (distance < inner || distance > outer) continue;
      const angle = (Math.atan2(dy, dx) + Math.PI) / (2 * Math.PI);
      // Mitad de cada trazo encendida, mitad apagada.
      if (Math.floor(angle * dashes * 2) % 2 === 1) continue;
      const offset = (y * size + x) * 4;
      pixels.set([226, 232, 240, 235], offset);
    }
  }
  return pixels;
}

// Ficha de una nota: arriba a la derecha del punto, unida por una línea guía.
export const CALLOUT_GAP_X = 46;
export const CALLOUT_RISE_Y = 36;
// Distancia mínima de la ficha a los bordes del mapa.
export const CALLOUT_MARGIN = 12;
// La línea llega al borde de la ficha, no a su esquina.
const CALLOUT_LINE_INSET = 16;

export interface CalloutPlacement {
  left: number;
  top: number;
  lineX: number;
  lineY: number;
}

/**
 * Dónde dibujar la ficha para que nunca se salga del mapa.
 *
 * Prefiere arriba a la derecha del punto; si no cabe arriba, la baja; si no
 * cabe a la derecha, la pasa a la izquierda.
 *
 * @param point Punto de la nota en pantalla.
 * @param card Ancho y alto de la ficha.
 * @param viewport Ancho y alto del mapa.
 */
export function calloutPlacement(
  point: { x: number; y: number },
  card: { width: number; height: number },
  viewport: { width: number; height: number },
): CalloutPlacement {
  const fitsRight = point.x + CALLOUT_GAP_X + card.width <= viewport.width - CALLOUT_MARGIN;
  const left = fitsRight ? point.x + CALLOUT_GAP_X : point.x - CALLOUT_GAP_X - card.width;
  const preferredTop = point.y - CALLOUT_RISE_Y - card.height;
  const maxTop = Math.max(CALLOUT_MARGIN, viewport.height - card.height - CALLOUT_MARGIN);
  const top = Math.min(maxTop, Math.max(CALLOUT_MARGIN, preferredTop));
  const lineY = Math.min(
    top + card.height - CALLOUT_LINE_INSET,
    Math.max(top + CALLOUT_LINE_INSET, point.y - CALLOUT_RISE_Y),
  );
  return { left, top, lineX: fitsRight ? left : left + card.width, lineY };
}
