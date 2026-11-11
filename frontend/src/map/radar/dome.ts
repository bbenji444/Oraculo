/**
 * Radar en 3D: una cúpula de luz sobre la zona que se busca (Benji,
 * 11/11/2026: «que se hiciera como una tipo cúpula en 3D sobre el área que
 * estamos seleccionando, para que vaya acorde al mapa 3D del globo»).
 *
 * - **Cúpula:** media esfera achatada, de vidrio cian, con meridianos y
 *   paralelos, el borde encendido y el haz del radar que la recorre girando.
 * - **Piso:** disco sobre el terreno con anillos fijos, una onda que se
 *   expande y el mismo haz.
 * - **Ecos:** un punto que late sobre el terreno por cada nota encontrada
 *   (capas de círculo de MapLibre, dentro de la cúpula).
 *
 * Se dibuja con una capa propia de MapLibre (`CustomLayerInterface`, modo 3D),
 * igual que los arcos del muro (map/muro/engine.ts): la altura sube sobre la
 * esfera con `projectToSphere` y lo que queda detrás del horizonte se recorta
 * con `globeComputeClippingZ`. Sin dependencias nuevas.
 *
 * No hace: no mueve la cámara ni sabe de búsquedas; recibe centro y tamaño.
 */
import {
  type CustomLayerInterface,
  type CustomRenderMethodInput,
  type GeoJSONSource,
  type Map as MapLibreMap,
  MercatorCoordinate,
} from 'maplibre-gl';

import { metersInMercatorUnits } from '../muro/geometry';

const DOME_LAYER = 'radar-dome';
const BLIPS_SOURCE = 'radar-blips';
const BLIPS_HALO = 'radar-blips-halo';
const BLIPS_CORE = 'radar-blips-core';

// Radio medio de la Tierra (m), el mismo que usa MapLibre para el globo.
const EARTH_RADIUS_M = 6_371_008.8;
const DEG = Math.PI / 180;
// Resolución de la malla: 24 anillos × 64 gajos se ven redondos de cerca.
const RINGS = 24;
const SEGMENTS = 64;
// La cúpula es achatada: su altura es este tanto del radio (alta se vería como globo).
const HEIGHT_SHARE = 0.42;
// Límites del radio: un municipio pequeño necesita cúpula visible; todo un
// país no debe tapar medio planeta.
const MIN_RADIUS_M = 8_000;
const MAX_RADIUS_M = 1_600_000;
// Un poco más ancha que la región: la abarca con aire alrededor.
const RADIUS_PADDING = 1.1;
// Metros por grado de latitud.
const METERS_PER_DEGREE = 111_320;
// Los ecos caen dentro de este tanto del radio.
const BLIP_SPREAD = 0.8;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
// Mezcla del plano y el globo (igual que map/muro/engine.ts).
const Z_GLOBENESS_THRESHOLD = 0.2;

/** Rectángulo [oeste, sur, este, norte] en grados. */
export type Bbox = readonly [number, number, number, number];

export interface DomeShape {
  /** Centro [lng, lat]. */
  center: [number, number];
  /** Radio sobre el terreno, en metros. */
  radiusM: number;
  /** Altura de la cima, en metros. */
  heightM: number;
}

/**
 * Centro y tamaño de la cúpula a partir del rectángulo de la región.
 *
 * @example domeShape([-117.1, 14.5, -86.7, 32.7]) // todo México: radio 1 600 km
 */
export function domeShape(bbox: Bbox): DomeShape {
  const [west, south, east, north] = bbox;
  const center: [number, number] = [(west + east) / 2, (south + north) / 2];
  const width = (east - west) * METERS_PER_DEGREE * Math.cos(center[1] * DEG);
  const height = (north - south) * METERS_PER_DEGREE;
  const radiusM = Math.min(
    MAX_RADIUS_M,
    Math.max(MIN_RADIUS_M, (Math.max(width, height) / 2) * RADIUS_PADDING),
  );
  return { center, radiusM, heightM: radiusM * HEIGHT_SHARE };
}

/**
 * Distancia en grados entre dos puntos sobre la esfera (para saber si la zona
 * está del otro lado del globo).
 *
 * @example angularDistance([-99, 19], [10, 50]) // ≈ 88°
 */
export function angularDistance(a: [number, number], b: [number, number]): number {
  const [lng1, lat1] = [a[0] * DEG, a[1] * DEG];
  const [lng2, lat2] = [b[0] * DEG, b[1] * DEG];
  const h =
    Math.sin((lat2 - lat1) / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin((lng2 - lng1) / 2) ** 2;
  return (2 * Math.asin(Math.min(1, Math.sqrt(h)))) / DEG;
}

/**
 * El punto a `distance` metros del centro en el rumbo `bearing` (radianes),
 * sobre la esfera.
 */
export function destination(
  center: [number, number],
  distance: number,
  bearing: number,
): [number, number] {
  const lat1 = center[1] * DEG;
  const lng1 = center[0] * DEG;
  const delta = distance / EARTH_RADIUS_M;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(delta) + Math.cos(lat1) * Math.sin(delta) * Math.cos(bearing),
  );
  const lng2 =
    lng1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(delta) * Math.cos(lat1),
      Math.cos(delta) - Math.sin(lat1) * Math.sin(lat2),
    );
  return [lng2 / DEG, lat2 / DEG];
}

// Por vértice: posición Mercator (2), altura en metros (1), altura en
// unidades Mercator (1), azimut 0–1, radio 0–1 y tipo (0 cúpula, 1 piso).
const STRIDE = 7;

/**
 * Malla de la cúpula y del piso.
 *
 * @returns Vértices intercalados e índices de triángulos.
 */
export function domeMesh(shape: DomeShape, rings = RINGS, segments = SEGMENTS) {
  const floats: number[] = [];
  const indices: number[] = [];
  const grid = (kind: 0 | 1) => {
    const start = floats.length / STRIDE;
    for (let i = 0; i <= rings; i += 1) {
      const t = i / rings;
      // Cúpula: de la cima (φ = 0) a la base (φ = 90°). Piso: del centro al borde.
      const phi = (t * Math.PI) / 2;
      const ground = kind === 0 ? shape.radiusM * Math.sin(phi) : shape.radiusM * t;
      const meters = kind === 0 ? shape.heightM * Math.cos(phi) : 0;
      for (let j = 0; j <= segments; j += 1) {
        const u = j / segments;
        const [lng, lat] = destination(shape.center, ground, u * 2 * Math.PI);
        const m = MercatorCoordinate.fromLngLat([lng, lat]);
        floats.push(m.x, m.y, meters, metersInMercatorUnits(lat, meters), u, t, kind);
      }
    }
    for (let i = 0; i < rings; i += 1) {
      for (let j = 0; j < segments; j += 1) {
        const a = start + i * (segments + 1) + j;
        const b = a + segments + 1;
        indices.push(a, b, a + 1, a + 1, b, b + 1);
      }
    }
  };
  grid(1);
  grid(0);
  return { floats: new Float32Array(floats), indices: new Uint32Array(indices) };
}

/**
 * Dónde caen los ecos: espiral dorada dentro de la cúpula, siempre los mismos
 * lugares para el mismo número (no saltan al llegar notas nuevas).
 */
export function blipPoints(shape: DomeShape, count: number): [number, number][] {
  return Array.from({ length: Math.max(0, count) }, (_, i) => {
    const r = Math.sqrt((i + 0.5) / Math.max(count, 1)) * BLIP_SPREAD * shape.radiusM;
    return destination(shape.center, r, i * GOLDEN_ANGLE);
  });
}

const VERTEX = `
in vec2 a_pos;
in float a_elev;
in float a_elev_flat;
in vec3 a_uvk;
out vec3 v_uvk;
vec4 projectPoint(vec2 mercator, float meters, float flatElevation) {
#ifdef GLOBE
  vec3 elevated = projectToSphere(mercator) * (1.0 + meters / GLOBE_RADIUS);
  vec4 globePosition = u_projection_matrix * vec4(elevated, 1.0);
  globePosition.z = globeComputeClippingZ(elevated) * globePosition.w;
  if (u_projection_transition > 0.999) return globePosition;
  vec4 flatPosition = u_projection_fallback_matrix * vec4(mercator, flatElevation, 1.0);
  vec4 result = globePosition;
  result.xyw = mix(flatPosition.xyw, globePosition.xyw, u_projection_transition);
  float globeness = (u_projection_transition - ${Z_GLOBENESS_THRESHOLD.toFixed(1)}) / ${(1 - Z_GLOBENESS_THRESHOLD).toFixed(1)};
  result.z = mix(0.0, globePosition.z, clamp(globeness, 0.0, 1.0));
  return result;
#else
  return u_projection_matrix * vec4(mercator, flatElevation, 1.0);
#endif
}
void main() {
  gl_Position = projectPoint(a_pos, a_elev, a_elev_flat);
  v_uvk = a_uvk;
}`;

// Vidrio cian: rejilla, borde encendido y el haz del radar que gira; en el
// piso, anillos fijos y una onda que se expande. Mezcla aditiva (luz).
const FRAGMENT = `#version 300 es
precision highp float;
in vec3 v_uvk;
uniform float u_time;
out vec4 fragColor;
const float TAU = 6.2831853;
float line(float value, float count, float width) {
  float d = abs(fract(value * count + 0.5) - 0.5);
  return 1.0 - smoothstep(0.0, width, d);
}
void main() {
  float u = v_uvk.x;
  float r = v_uvk.y;
  float sweep = mod(u_time * 1.6, TAU);
  float behind = mod(sweep - u * TAU + TAU, TAU);
  float beam = exp(-behind * 2.4);
  float a;
  if (v_uvk.z < 0.5) {
    float grid = max(line(u, 12.0, 0.04), line(r, 6.0, 0.05));
    a = 0.035 + 0.22 * pow(r, 3.0) + 0.22 * grid + 0.35 * beam * (0.25 + 0.75 * r);
  } else {
    float wave = exp(-pow((r - fract(u_time * 0.35)) * 22.0, 2.0));
    float rings = line(r, 4.0, 0.04) * 0.6;
    float edge = smoothstep(0.95, 1.0, r);
    a = 0.04 + 0.25 * rings + 0.35 * wave + 0.5 * edge + 0.45 * beam;
  }
  vec3 cyan = vec3(0.0, 0.82, 1.0);
  fragColor = vec4(cyan * a, a);
}`;

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error('WebGL no pudo crear el shader del radar.');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(`Shader del radar: ${gl.getShaderInfoLog(shader) ?? 'error'}`);
  }
  return shader;
}

/** La capa de la cúpula y su piso. */
class DomeLayer implements CustomLayerInterface {
  readonly id = DOME_LAYER;
  readonly type = 'custom' as const;
  readonly renderingMode = '3d' as const;
  private map: MapLibreMap | null = null;
  private program: WebGLProgram | null = null;
  private programKey = '';
  private vao: WebGLVertexArrayObject | null = null;
  private buffers: WebGLBuffer[] = [];
  private indexCount = 0;
  /** Si gira el haz (sin animación del sistema: quieto). */
  animate = true;

  private readonly shape: DomeShape;

  constructor(shape: DomeShape) {
    this.shape = shape;
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    const { floats, indices } = domeMesh(this.shape);
    this.vao = gl.createVertexArray();
    const vbo = gl.createBuffer();
    const ibo = gl.createBuffer();
    this.buffers = [vbo, ibo];
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, floats, gl.STATIC_DRAW);
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
    gl.bindVertexArray(null);
    this.indexCount = indices.length;
  }

  private ensureProgram(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): WebGLProgram {
    const { shaderData } = args;
    if (this.program && this.programKey === shaderData.variantName) return this.program;
    const vertex = `#version 300 es\n${shaderData.vertexShaderPrelude}\n${shaderData.define}\n${VERTEX}`;
    const program = gl.createProgram();
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, vertex));
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`Programa del radar: ${gl.getProgramInfoLog(program) ?? 'error'}`);
    }
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffers[0] ?? null);
    const attributes: [string, number, number][] = [
      ['a_pos', 2, 0],
      ['a_elev', 1, 2],
      ['a_elev_flat', 1, 3],
      ['a_uvk', 3, 4],
    ];
    for (const [name, size, offset] of attributes) {
      const location = gl.getAttribLocation(program, name);
      if (location >= 0) {
        gl.enableVertexAttribArray(location);
        gl.vertexAttribPointer(location, size, gl.FLOAT, false, STRIDE * 4, offset * 4);
      }
    }
    gl.bindVertexArray(null);
    this.program = program;
    this.programKey = shaderData.variantName;
    return program;
  }

  render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): void {
    if (!this.map || !this.vao || this.indexCount === 0) return;
    const program = this.ensureProgram(gl, args);
    const projection = args.defaultProjectionData;
    const uniform = (name: string) => gl.getUniformLocation(program, name);
    gl.useProgram(program);
    gl.uniformMatrix4fv(
      uniform('u_projection_matrix'),
      false,
      new Float32Array(projection.mainMatrix),
    );
    gl.uniform4f(uniform('u_projection_tile_mercator_coords'), ...projection.tileMercatorCoords);
    gl.uniform4f(uniform('u_projection_clipping_plane'), ...projection.clippingPlane);
    gl.uniform1f(uniform('u_projection_transition'), projection.projectionTransition);
    gl.uniformMatrix4fv(
      uniform('u_projection_fallback_matrix'),
      false,
      new Float32Array(projection.fallbackMatrix),
    );
    gl.uniform1f(uniform('u_time'), this.animate ? performance.now() / 1000 : 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.DEPTH_TEST);
    gl.depthMask(false);
    gl.bindVertexArray(this.vao);
    gl.drawElements(gl.TRIANGLES, this.indexCount, gl.UNSIGNED_INT, 0);
    gl.bindVertexArray(null);
    // Mientras se busca, el haz gira: se pide el siguiente cuadro.
    if (this.animate) this.map.triggerRepaint();
  }

  onRemove(_map: MapLibreMap, gl: WebGL2RenderingContext): void {
    if (this.vao) gl.deleteVertexArray(this.vao);
    for (const buffer of this.buffers) gl.deleteBuffer(buffer);
    if (this.program) gl.deleteProgram(this.program);
    this.vao = null;
    this.buffers = [];
    this.program = null;
    this.map = null;
  }
}

/** Cómo actualizar o quitar el radar 3D. */
export interface DomeRadar {
  /** Muestra tantos ecos como notas encontradas. */
  setBlips(count: number): void;
  remove(): void;
}

/** Los ecos como GeoJSON (puntos sin propiedades). */
interface BlipCollection {
  type: 'FeatureCollection';
  features: {
    type: 'Feature';
    id: number;
    properties: Record<string, never>;
    geometry: { type: 'Point'; coordinates: [number, number] };
  }[];
}

function blipData(shape: DomeShape, count: number): BlipCollection {
  return {
    type: 'FeatureCollection',
    features: blipPoints(shape, count).map((coordinates, index) => ({
      type: 'Feature',
      id: index,
      properties: {},
      geometry: { type: 'Point', coordinates },
    })),
  };
}

/**
 * Pone la cúpula sobre la región y devuelve cómo actualizarla.
 *
 * @param map Mapa ya cargado.
 * @param bbox Rectángulo de la región buscada.
 * @param animate Si el haz gira (falso con «Menos movimiento»).
 */
export function addDomeRadar(map: MapLibreMap, bbox: Bbox, animate = true): DomeRadar {
  const shape = domeShape(bbox);
  const dome = new DomeLayer(shape);
  dome.animate = animate;
  map.addLayer(dome);
  map.addSource(BLIPS_SOURCE, { type: 'geojson', data: blipData(shape, 0) });
  map.addLayer({
    id: BLIPS_HALO,
    type: 'circle',
    source: BLIPS_SOURCE,
    paint: {
      'circle-radius': 11,
      'circle-color': '#00d2ff',
      'circle-blur': 1,
      'circle-opacity': 0.55,
      'circle-pitch-alignment': 'map',
    },
  });
  map.addLayer({
    id: BLIPS_CORE,
    type: 'circle',
    source: BLIPS_SOURCE,
    paint: {
      'circle-radius': 3.5,
      'circle-color': '#e7fbff',
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#00d2ff',
      'circle-pitch-alignment': 'map',
    },
  });
  let shown = -1;
  return {
    setBlips(count) {
      if (count === shown) return;
      shown = count;
      void map.getSource<GeoJSONSource>(BLIPS_SOURCE)?.setData(blipData(shape, count));
    },
    remove() {
      for (const id of [BLIPS_CORE, BLIPS_HALO, DOME_LAYER]) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
      if (map.getSource(BLIPS_SOURCE)) map.removeSource(BLIPS_SOURCE);
    },
  };
}
