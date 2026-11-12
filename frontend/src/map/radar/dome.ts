/**
 * Radar en 3D: una cúpula de luz sobre la zona que se busca (Benji,
 * 11/11/2026: «que se hiciera como una tipo cúpula en 3D sobre el área que
 * estamos seleccionando, para que vaya acorde al mapa 3D del globo»).
 *
 * - **Cúpula:** media esfera achatada, de vidrio cian, con meridianos y
 *   paralelos, el borde encendido y el haz del radar que la recorre girando.
 * - **Piso:** disco sobre el terreno con anillos fijos, una onda que se
 *   expande y el mismo haz.
 * - **Contactos:** por cada nota encontrada se levanta una columna de luz
 *   desde el piso hasta casi tocar la cúpula, con un destello al aparecer y
 *   una onda que se abre en su base (Benji, 11/11/2026: «en vez de puntos
 *   algún tipo de efecto distinto», que se vea más profesional).
 *
 * Se dibuja con una capa propia de MapLibre (`CustomLayerInterface`, modo 3D),
 * igual que los arcos del muro (map/muro/engine.ts): la altura sube sobre la
 * esfera con `projectToSphere` y lo que queda detrás del horizonte se recorta
 * con `globeComputeClippingZ`. Sin dependencias nuevas.
 *
 * No hace: no mueve la cámara ni sabe de búsquedas; recibe centro, tamaño y
 * cuántas notas van.
 */
import {
  type CustomLayerInterface,
  type CustomRenderMethodInput,
  type Map as MapLibreMap,
  MercatorCoordinate,
} from 'maplibre-gl';

import { metersInMercatorUnits } from '../muro/geometry';

const DOME_LAYER = 'radar-dome';

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
// Los contactos caen dentro de este tanto del radio (lejos del borde).
const CONTACT_SPREAD = 0.8;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
// Parte fraccionaria de la razón áurea: reparte los radios sin amontonarlos.
const GOLDEN_FRACTION = 0.6180339887;
// Mezcla del plano y el globo (igual que map/muro/engine.ts).
const Z_GLOBENESS_THRESHOLD = 0.2;

/** Columnas a la vista como máximo: más ya no se distinguen. */
export const MAX_CONTACTS = 24;
// Columna: grosor como tanto del radio de la cúpula, con límites para que no
// desaparezca en un municipio ni se vuelva un tubo en todo el país.
const PILLAR_RADIUS_SHARE = 0.012;
const PILLAR_MIN_RADIUS_M = 350;
const PILLAR_MAX_RADIUS_M = 14_000;
// La columna llega a este tanto de la cúpula encima de ella (no la atraviesa).
const PILLAR_REACH = 0.88;
const PILLAR_SEGMENTS = 10;
const PILLAR_RINGS = 6;
// Onda en la base de cada columna.
const RIPPLE_RADIUS_SHARE = 0.09;
const RIPPLE_SEGMENTS = 32;
const RIPPLE_RINGS = 6;
// Si llegan varias notas de golpe, se encienden una tras otra (segundos).
const CONTACT_STAGGER_S = 0.18;

// Qué es cada vértice (va en el shader como número).
const KIND_DOME = 0;
const KIND_FLOOR = 1;
const KIND_PILLAR = 2;
const KIND_RIPPLE = 3;

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
 * Distancia en grados entre dos puntos sobre la esfera.
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
// unidades Mercator (1), u, t, tipo (3), nacimiento en segundos (1) y una
// semilla 0–1 para que cada contacto lata a su ritmo (1).
const STRIDE = 9;

/** Vértices intercalados e índices de triángulos. */
interface Mesh {
  floats: Float32Array;
  indices: Uint32Array;
}

/** Arma una malla de anillos × gajos; `place` da lugar y altura de cada vértice. */
function addGrid(
  floats: number[],
  indices: number[],
  rings: number,
  segments: number,
  kind: number,
  extra: [birth: number, seed: number],
  place: (t: number, u: number) => [lng: number, lat: number, meters: number],
): void {
  const start = floats.length / STRIDE;
  for (let i = 0; i <= rings; i += 1) {
    const t = i / rings;
    for (let j = 0; j <= segments; j += 1) {
      const u = j / segments;
      const [lng, lat, meters] = place(t, u);
      const m = MercatorCoordinate.fromLngLat([lng, lat]);
      floats.push(m.x, m.y, meters, metersInMercatorUnits(lat, meters), u, t, kind, ...extra);
    }
  }
  for (let i = 0; i < rings; i += 1) {
    for (let j = 0; j < segments; j += 1) {
      const a = start + i * (segments + 1) + j;
      const b = a + segments + 1;
      indices.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
}

/**
 * Malla de la cúpula y del piso.
 *
 * @returns Vértices intercalados (primero el piso) e índices de triángulos.
 */
export function domeMesh(shape: DomeShape, rings = RINGS, segments = SEGMENTS): Mesh {
  const floats: number[] = [];
  const indices: number[] = [];
  // Piso: del centro al borde, pegado al terreno.
  addGrid(floats, indices, rings, segments, KIND_FLOOR, [0, 0], (t, u) => [
    ...destination(shape.center, shape.radiusM * t, u * 2 * Math.PI),
    0,
  ]);
  // Cúpula: de la cima (φ = 0) a la base (φ = 90°).
  addGrid(floats, indices, rings, segments, KIND_DOME, [0, 0], (t, u) => {
    const phi = (t * Math.PI) / 2;
    return [
      ...destination(shape.center, shape.radiusM * Math.sin(phi), u * 2 * Math.PI),
      shape.heightM * Math.cos(phi),
    ];
  });
  return { floats: new Float32Array(floats), indices: new Uint32Array(indices) };
}

/** Dónde cae un contacto: distancia al centro (m) y rumbo (radianes). */
interface ContactSpot {
  distanceM: number;
  bearing: number;
  point: [number, number];
}

function contactSpot(shape: DomeShape, index: number): ContactSpot {
  // Radio con la razón áurea y ángulo con el ángulo áureo: cada contacto
  // tiene su lugar fijo, sin importar cuántos haya (no brincan al llegar más).
  const share = Math.sqrt((0.5 + index * GOLDEN_FRACTION) % 1);
  const distanceM = share * CONTACT_SPREAD * shape.radiusM;
  const bearing = index * GOLDEN_ANGLE;
  return { distanceM, bearing, point: destination(shape.center, distanceM, bearing) };
}

/**
 * Dónde caen los contactos: siempre el mismo lugar para el mismo número de
 * contacto, repartidos dentro de la cúpula.
 */
export function contactPoints(shape: DomeShape, count: number): [number, number][] {
  return Array.from({ length: Math.max(0, count) }, (_, i) => contactSpot(shape, i).point);
}

/**
 * Malla de las columnas de luz y de las ondas de sus bases.
 *
 * @param births Segundo en que se encendió cada contacto (uno por columna).
 */
export function contactMesh(shape: DomeShape, births: readonly number[]): Mesh {
  const floats: number[] = [];
  const indices: number[] = [];
  const pillarRadius = Math.min(
    PILLAR_MAX_RADIUS_M,
    Math.max(PILLAR_MIN_RADIUS_M, shape.radiusM * PILLAR_RADIUS_SHARE),
  );
  births.forEach((birth, index) => {
    const spot = contactSpot(shape, index);
    // Altura de la cúpula encima del contacto: la columna casi la toca.
    const under = spot.distanceM / shape.radiusM;
    const reach = PILLAR_REACH * shape.heightM * Math.sqrt(Math.max(0, 1 - under * under));
    const seed = (index * GOLDEN_FRACTION) % 1;
    addGrid(floats, indices, PILLAR_RINGS, PILLAR_SEGMENTS, KIND_PILLAR, [birth, seed], (t, u) => [
      ...destination(spot.point, pillarRadius, u * 2 * Math.PI),
      reach * t,
    ]);
    addGrid(floats, indices, RIPPLE_RINGS, RIPPLE_SEGMENTS, KIND_RIPPLE, [birth, seed], (t, u) => [
      ...destination(spot.point, shape.radiusM * RIPPLE_RADIUS_SHARE * t, u * 2 * Math.PI),
      0,
    ]);
  });
  return { floats: new Float32Array(floats), indices: new Uint32Array(indices) };
}

/**
 * Cuándo se enciende cada contacto: los que ya estaban no cambian y los
 * nuevos se encienden uno tras otro desde `now`.
 *
 * @example contactBirths([3], 3, 10) // [3, 10.18, 10.36]
 */
export function contactBirths(previous: readonly number[], count: number, now: number): number[] {
  const wanted = Math.min(MAX_CONTACTS, Math.max(0, count));
  const kept = previous.slice(0, wanted);
  const added = Array.from(
    { length: wanted - kept.length },
    (_, i) => now + (i + (kept.length > 0 ? 1 : 0)) * CONTACT_STAGGER_S,
  );
  return [...kept, ...added];
}

const VERTEX = `
in vec2 a_pos;
in float a_elev;
in float a_elev_flat;
in vec3 a_uvk;
in float a_birth;
in float a_seed;
uniform float u_time;
uniform float u_still;
out vec3 v_uvk;
out float v_age;
out float v_seed;
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
  // Sin animación todo aparece ya encendido y quieto.
  float age = u_still > 0.5 ? 100.0 : u_time - a_birth;
  // La columna sube desde el piso en casi un segundo al encenderse.
  float grow = abs(a_uvk.z - ${KIND_PILLAR.toFixed(1)}) < 0.5
    ? smoothstep(0.0, 1.0, clamp(age / 0.9, 0.0, 1.0))
    : 1.0;
  gl_Position = projectPoint(a_pos, a_elev * grow, a_elev_flat * grow);
  v_uvk = a_uvk;
  v_age = age;
  v_seed = a_seed;
}`;

// Vidrio cian: rejilla, borde encendido y el haz del radar que gira; en el
// piso, anillos fijos y una onda que se expande. Los contactos son luz
// blanca que se vuelve cian hacia arriba, con un destello al encenderse.
// Mezcla aditiva (luz).
const FRAGMENT = `#version 300 es
precision highp float;
in vec3 v_uvk;
in float v_age;
in float v_seed;
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
  float kind = v_uvk.z;
  vec3 cyan = vec3(0.0, 0.82, 1.0);
  vec3 white = vec3(0.85, 0.98, 1.0);
  if (v_age < 0.0) discard;
  if (kind > ${(KIND_PILLAR - 0.5).toFixed(1)}) {
    float flash = exp(-v_age * 2.2);
    if (kind < ${(KIND_RIPPLE - 0.5).toFixed(1)}) {
      // Columna: r es la altura (0 abajo, 1 arriba).
      float fade = pow(1.0 - r, 1.4);
      float flicker = 0.85 + 0.15 * sin(u_time * 7.0 + v_seed * 40.0);
      float a = (0.12 + 0.5 * fade) * flicker + 0.9 * flash * fade;
      fragColor = vec4(mix(cyan, white, 0.35 + 0.5 * fade) * a, a);
    } else {
      // Base: un núcleo encendido y una onda que se abre una y otra vez.
      float phase = fract(v_age * 0.45 + v_seed);
      float ring = exp(-pow((r - phase) * 12.0, 2.0)) * (1.0 - phase);
      float core = exp(-r * 10.0);
      float a = 0.55 * ring + 0.55 * core + 0.7 * flash * (1.0 - r);
      fragColor = vec4(mix(cyan, white, core) * a, a);
    }
    return;
  }
  float sweep = mod(u_time * 1.6, TAU);
  float behind = mod(sweep - u * TAU + TAU, TAU);
  float beam = exp(-behind * 2.4);
  float a;
  if (kind < 0.5) {
    float grid = max(line(u, 12.0, 0.04), line(r, 6.0, 0.05));
    a = 0.035 + 0.22 * pow(r, 3.0) + 0.22 * grid + 0.35 * beam * (0.25 + 0.75 * r);
  } else {
    float wave = exp(-pow((r - fract(u_time * 0.35)) * 22.0, 2.0));
    float rings = line(r, 4.0, 0.04) * 0.6;
    float edge = smoothstep(0.95, 1.0, r);
    a = 0.04 + 0.25 * rings + 0.35 * wave + 0.5 * edge + 0.45 * beam;
  }
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

/** Una malla en la tarjeta de video: su VAO, sus búferes y cuántos índices tiene. */
interface GpuMesh {
  vao: WebGLVertexArrayObject;
  vbo: WebGLBuffer;
  ibo: WebGLBuffer;
  count: number;
}

function createMesh(gl: WebGL2RenderingContext): GpuMesh {
  const vao = gl.createVertexArray();
  const vbo = gl.createBuffer();
  const ibo = gl.createBuffer();
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo);
  gl.bindVertexArray(null);
  return { vao, vbo, ibo, count: 0 };
}

function upload(gl: WebGL2RenderingContext, target: GpuMesh, mesh: Mesh): void {
  gl.bindBuffer(gl.ARRAY_BUFFER, target.vbo);
  gl.bufferData(gl.ARRAY_BUFFER, mesh.floats, gl.STATIC_DRAW);
  gl.bindVertexArray(target.vao);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, gl.STATIC_DRAW);
  gl.bindVertexArray(null);
  target.count = mesh.indices.length;
}

/** La capa de la cúpula, su piso y los contactos. */
class DomeLayer implements CustomLayerInterface {
  readonly id = DOME_LAYER;
  readonly type = 'custom' as const;
  readonly renderingMode = '3d' as const;
  private map: MapLibreMap | null = null;
  private program: WebGLProgram | null = null;
  private programKey = '';
  private dome: GpuMesh | null = null;
  private contacts: GpuMesh | null = null;
  private births: number[] = [];
  // Los contactos cambiaron y falta subirlos a la tarjeta de video.
  private contactsDirty = true;
  /** Si gira el haz (sin animación del sistema: quieto). */
  animate = true;

  private readonly shape: DomeShape;

  constructor(shape: DomeShape) {
    this.shape = shape;
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    this.dome = createMesh(gl);
    upload(gl, this.dome, domeMesh(this.shape));
    this.contacts = createMesh(gl);
  }

  /** Cambia los contactos encendidos (sus segundos de nacimiento). */
  setContacts(births: number[]): void {
    this.births = births;
    // Se suben en el siguiente cuadro: tocar WebGL fuera de `render` le
    // movería a MapLibre el estado que tiene guardado.
    this.contactsDirty = true;
    this.map?.triggerRepaint();
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
    const attributes: [string, number, number][] = [
      ['a_pos', 2, 0],
      ['a_elev', 1, 2],
      ['a_elev_flat', 1, 3],
      ['a_uvk', 3, 4],
      ['a_birth', 1, 7],
      ['a_seed', 1, 8],
    ];
    for (const mesh of [this.dome, this.contacts]) {
      if (!mesh) continue;
      gl.bindVertexArray(mesh.vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, mesh.vbo);
      for (const [name, size, offset] of attributes) {
        const location = gl.getAttribLocation(program, name);
        if (location >= 0) {
          gl.enableVertexAttribArray(location);
          gl.vertexAttribPointer(location, size, gl.FLOAT, false, STRIDE * 4, offset * 4);
        }
      }
    }
    gl.bindVertexArray(null);
    this.program = program;
    this.programKey = shaderData.variantName;
    return program;
  }

  render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): void {
    if (!this.map || !this.dome || this.dome.count === 0) return;
    if (this.contactsDirty && this.contacts) {
      upload(gl, this.contacts, contactMesh(this.shape, this.births));
      this.contactsDirty = false;
    }
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
    gl.uniform1f(uniform('u_still'), this.animate ? 0 : 1);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.DEPTH_TEST);
    gl.depthMask(false);
    for (const mesh of [this.dome, this.contacts]) {
      if (!mesh || mesh.count === 0) continue;
      gl.bindVertexArray(mesh.vao);
      gl.drawElements(gl.TRIANGLES, mesh.count, gl.UNSIGNED_INT, 0);
    }
    gl.bindVertexArray(null);
    // Mientras se busca, el haz gira: se pide el siguiente cuadro.
    if (this.animate) this.map.triggerRepaint();
  }

  onRemove(_map: MapLibreMap, gl: WebGL2RenderingContext): void {
    for (const mesh of [this.dome, this.contacts]) {
      if (!mesh) continue;
      gl.deleteVertexArray(mesh.vao);
      gl.deleteBuffer(mesh.vbo);
      gl.deleteBuffer(mesh.ibo);
    }
    if (this.program) gl.deleteProgram(this.program);
    this.dome = null;
    this.contacts = null;
    this.program = null;
    this.map = null;
  }
}

/** Cómo actualizar o quitar el radar 3D. */
export interface DomeRadar {
  /** Enciende una columna por nota encontrada (hasta {@link MAX_CONTACTS}). */
  setBlips(count: number): void;
  remove(): void;
}

/**
 * Pone la cúpula sobre la región y devuelve cómo actualizarla.
 *
 * @param map Mapa ya cargado.
 * @param bbox Rectángulo de la región buscada.
 * @param animate Si el haz gira y las columnas suben (falso con «Menos movimiento»).
 */
export function addDomeRadar(map: MapLibreMap, bbox: Bbox, animate = true): DomeRadar {
  const dome = new DomeLayer(domeShape(bbox));
  dome.animate = animate;
  map.addLayer(dome);
  let births: number[] = [];
  return {
    setBlips(count) {
      const next = contactBirths(births, count, performance.now() / 1000);
      if (next.length === births.length) return;
      births = next;
      dome.setContacts(births);
    },
    remove() {
      if (map.getLayer(DOME_LAYER)) map.removeLayer(DOME_LAYER);
    },
  };
}
