/**
 * Radar de «Todo el mundo» (ADR-0116): una esfera tenue de vidrio que envuelve
 * a la Tierra entera mientras se busca en la región «Mundo» (ADR-0112).
 *
 * Benji (18/11/2026): en «Todo el mundo», en lugar de la cúpula, «una esfera
 * tenue que envuelva toda la Tierra con la misma textura de la cúpula y una
 * animación chida solo mientras se busca». La cúpula (dome.ts) se pensó para
 * una zona: con el rectángulo del mundo caía en Ghana con 1,600 km de radio.
 *
 * - **Vidrio:** el mismo material de la cúpula (cian, mezcla aditiva, 12
 *   meridianos y 6 paralelos), más tenue y encendido hacia el borde.
 * - **Aparición:** la esfera sube del suelo a su altura mientras un frente de
 *   luz la recorre de sur a norte y va descubriendo la rejilla.
 * - **Mientras se busca:** un meridiano de luz le da la vuelta al planeta (el
 *   haz del radar), un anillo de latitud va y viene de polo a polo, el borde
 *   «respira» y cada nota encontrada enciende un ping en su lugar del
 *   planeta cuando el giro lo trae al frente.
 * - **Al terminar:** destello, la esfera se expande y se disuelve; luego se
 *   quita la capa.
 * - **«Menos movimiento»:** quieta, aparece y se quita al instante y nunca
 *   pide cuadros de más.
 *
 * Se dibuja con una capa propia de MapLibre (`CustomLayerInterface`, modo 3D),
 * como la cúpula. Cada vértice se pone sobre la esfera unitaria del globo
 * directo desde su longitud y latitud (sin pasar por Mercator, que no llega a
 * los polos) y lo que queda detrás de la Tierra se recorta con
 * `globeComputeClippingZ`. Solo se dibuja con el globo: de muy cerca (mapa
 * plano) no hay planeta que envolver.
 *
 * No hace: no mueve la cámara (el globo sigue girando dentro), no sabe de
 * búsquedas ni pone letreros; recibe cuántas notas van y cuándo terminar.
 */
import type {
  CustomLayerInterface,
  CustomRenderMethodInput,
  Map as MapLibreMap,
} from 'maplibre-gl';

import { easeOutCubic } from '../motion';
import {
  angularDistance,
  BEAM_SPEED_RAD_S,
  BEAM_TAIL,
  CONTACT_STAGGER_S,
  destination,
  GOLDEN_ANGLE,
  GOLDEN_FRACTION,
} from './dome';
import {
  type Attribute,
  bindAttributes,
  buildProgram,
  createMesh,
  deleteMesh,
  GLSL_GRID_LINE,
  glslFloat,
  GRID_MERIDIAN_WIDTH,
  GRID_MERIDIANS,
  GRID_PARALLEL_WIDTH,
  GRID_PARALLELS,
  type GpuMesh,
  type Mesh,
  setProjectionUniforms,
  type UniformLookup,
  uniformLookup,
  upload,
} from './gl';

/** Id de la capa en el mapa (hay una sola a la vez). */
export const SHELL_LAYER = 'radar-shell';

/**
 * Altura de la esfera sobre el terreno, como tanto del radio de la Tierra
 * (~380 km): a zoom 2 deja un halo de ~20 px alrededor del globo. Ajustada
 * con capturas (ADR-0116).
 */
export const SHELL_ALTITUDE_SHARE = 0.06;
/** Brillo de la esfera respecto a la cúpula: «tenue» (decisión de ADR-0116). */
export const SHELL_INTENSITY = 0.55;
/**
 * En modo día el brillo baja a este tanto: la luz aditiva sobre la textura
 * clara de la Tierra la lavaba.
 */
export const SHELL_DAY_SHARE = 0.6;
// Resolución de la malla: 48 anillos × 96 gajos se ven redondos a pantalla
// completa (~4,700 vértices, poco para la tarjeta de video).
const SHELL_RINGS = 48;
const SHELL_SEGMENTS = 96;

/** Segundos que tarda en aparecer (subir y descubrir la rejilla). */
export const REVEAL_S = 1.4;
/** Segundos que tarda en disolverse al terminar la búsqueda. */
export const DISSOLVE_S = 0.9;
/** Al disolverse, la altura crece hasta este tanto de la normal (se expande). */
export const DISSOLVE_LIFT = 1.5;
// La capa se quita un poco después de apagarse, para no cortar el último cuadro.
const DISSOLVE_MARGIN_MS = 120;
// El destello del cierre se apaga con esta potencia de lo que falta (cúbica:
// fuerte al principio y se va rápido).
const FLASH_POWER = 3;

/**
 * Lugares de los pings, repartidos por todo el planeta (Benji, 19/11/2026:
 * «esos puntos de la esfera solo aparecen en una parte del globo. Quiero que
 * aparezcan en todo el globo»). Con 40, el más cercano a cualquier punto de
 * la franja queda a menos de 30° y los discos (~6° de radio) no se enciman.
 */
export const SHELL_SPOTS = 40;
/**
 * Latitud máxima de los lugares. La vista general mira a 20° N y su borde
 * queda a ~78° del centro: un ping a 55° S todavía se ve; más al sur quedaría
 * de canto o detrás.
 */
export const SPOT_MAX_LAT_DEG = 55;
/**
 * Un lugar se enciende cuando el giro lo trae a menos de estos grados de
 * longitud del centro de la vista: así se ve nacer, en lugar de encenderse
 * detrás del planeta (la razón por la que el ADR-0116 los ponía todos al
 * frente). Con el globo girando, una vuelta los enciende todos.
 */
export const VISIBLE_LNG_DEG = 60;
// Radio del disco de cada ping sobre el vidrio (~6°): a zoom 2, unos 35 px.
const PING_RADIUS_M = 700_000;
const PING_RINGS = 8;
const PING_SEGMENTS = 32;

/**
 * Distancia de la cámara al centro de la Tierra (en radios terrestres) a la
 * que la esfera ya no se ve y a la que se ve completa. De cerca la cámara
 * quedaría dentro de la esfera y teñiría toda la pantalla: a zoom 2 la
 * distancia es ~5, a zoom 5 ~1.5 y a zoom 8 ~1.07 (calculado con el campo de
 * visión de MapLibre).
 */
export const CAMERA_FADE_NEAR = 1.2;
export const CAMERA_FADE_FAR = 1.6;
// MapLibre manda `projectionTransition` en 1 con el globo puro; abajo de esto
// se está pasando al mapa plano y la esfera no se dibuja.
const GLOBE_ONLY_TRANSITION = 0.999;
// Nombre de la variante de shaders del globo en MapLibre (`#define GLOBE`).
const GLOBE_VARIANT = 'globe';

const DEG = Math.PI / 180;

// Qué es cada vértice (va en el shader como número).
const KIND_SHELL = 0;
const KIND_PING = 1;

// Por vértice: longitud y latitud en grados (2), u, t, tipo (3), nacimiento
// en segundos (1) y una semilla 0–1 para que cada ping lata a su ritmo (1).
const STRIDE = 7;

const ATTRIBUTES: readonly Attribute[] = [
  ['a_lnglat', 2, 0],
  ['a_utk', 3, 2],
  ['a_birth', 1, 5],
  ['a_seed', 1, 6],
];

/**
 * Punto de la esfera unitaria para `[lng, lat]`, con la convención del globo
 * de MapLibre: `y` al norte y la longitud 0 hacia `+z`. Es el espejo en JS de
 * lo que hace el shader (y lo documenta la prueba).
 *
 * @param lng Longitud en grados (−180 a 180).
 * @param lat Latitud en grados (−90 a 90).
 * @returns `[x, y, z]` sobre la esfera de radio 1.
 *
 * @example spherePoint(90, 0) // [1, 0, 0]
 */
export function spherePoint(lng: number, lat: number): [number, number, number] {
  const l = lng * DEG;
  const p = lat * DEG;
  return [Math.sin(l) * Math.cos(p), Math.sin(p), Math.cos(l) * Math.cos(p)];
}

/** Arma una malla de anillos × gajos; `place` da `[lng, lat]` de cada vértice. */
function addGrid(
  floats: number[],
  indices: number[],
  rings: number,
  segments: number,
  kind: number,
  extra: [birth: number, seed: number],
  place: (t: number, u: number) => [lng: number, lat: number],
): void {
  const start = floats.length / STRIDE;
  for (let i = 0; i <= rings; i += 1) {
    const t = i / rings;
    for (let j = 0; j <= segments; j += 1) {
      const u = j / segments;
      floats.push(...place(t, u), u, t, kind, ...extra);
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
 * Malla de la esfera: de polo sur (`t = 0`) a polo norte (`t = 1`) y de la
 * longitud −180 (`u = 0`) a 180 (`u = 1`); la costura repite la columna.
 *
 * @param rings Anillos de latitud (por omisión, los que se ven redondos).
 * @param segments Gajos de longitud.
 * @returns Vértices intercalados e índices de triángulos.
 */
export function shellMesh(rings = SHELL_RINGS, segments = SHELL_SEGMENTS): Mesh {
  const floats: number[] = [];
  const indices: number[] = [];
  addGrid(floats, indices, rings, segments, KIND_SHELL, [0, 0], (t, u) => [
    -180 + 360 * u,
    -90 + 180 * t,
  ]);
  return { floats: new Float32Array(floats), indices: new Uint32Array(indices) };
}

/** Un ping sobre el vidrio: dónde, cuándo se encendió y su semilla. */
export interface Ping {
  point: [number, number];
  birth: number;
  seed: number;
}

/**
 * Los lugares fijos de los pings: una espiral de Fibonacci sobre la franja de
 * latitudes, que reparte {@link SHELL_SPOTS} puntos con la misma área cada
 * uno, en todo el planeta.
 *
 * @param count Cuántos lugares.
 * @returns `[lng, lat]` de cada uno, de norte a sur.
 *
 * @example globeSpots(40).length // 40
 */
export function globeSpots(count: number = SHELL_SPOTS): [number, number][] {
  const top = Math.sin(SPOT_MAX_LAT_DEG * DEG);
  return Array.from({ length: count }, (_, i) => {
    const z = top * (1 - (2 * (i + 0.5)) / count);
    const lng = (((i * GOLDEN_ANGLE) / DEG + 180) % 360) - 180;
    return [lng, Math.asin(z) / DEG];
  });
}

/** Grados de longitud entre dos meridianos, de 0 a 180. */
function lngGap(a: number, b: number): number {
  return Math.abs(((a - b + 540) % 360) - 180);
}

/**
 * Qué lugares libres se encienden ahora: los que el giro ya trajo al frente
 * (a menos de {@link VISIBLE_LNG_DEG} de longitud del centro), del más
 * cercano al centro al más lejano, hasta `wanted`.
 *
 * @param spots Todos los lugares ({@link globeSpots}).
 * @param taken Los que ya tienen ping.
 * @param center Centro de la cámara `[lng, lat]`.
 * @param wanted Cuántos pings faltan.
 * @returns Los lugares a encender, en orden.
 *
 * @example spotsInView(globeSpots(), new Set(), [-35, 20], 3) // los 3 más cercanos al Atlántico
 */
export function spotsInView(
  spots: readonly [number, number][],
  taken: ReadonlySet<string>,
  center: [number, number],
  wanted: number,
): [number, number][] {
  if (wanted <= 0) return [];
  return spots
    .filter((spot) => !taken.has(spot.join()) && lngGap(spot[0], center[0]) <= VISIBLE_LNG_DEG)
    .sort((a, b) => angularDistance(a, center) - angularDistance(b, center))
    .slice(0, wanted);
}

/**
 * Malla de los pings: un disco sobre el vidrio por cada uno (`t` va del
 * centro a la orilla), donde el shader abre un anillo con destello.
 *
 * @param pings Los pings encendidos, con su lugar, nacimiento y semilla.
 * @returns Vértices intercalados e índices de triángulos (vacíos sin pings).
 */
export function pingMesh(pings: readonly Ping[]): Mesh {
  const floats: number[] = [];
  const indices: number[] = [];
  for (const ping of pings) {
    addGrid(
      floats,
      indices,
      PING_RINGS,
      PING_SEGMENTS,
      KIND_PING,
      [ping.birth, ping.seed],
      (t, u) => destination(ping.point, PING_RADIUS_M * t, u * 2 * Math.PI),
    );
  }
  return { floats: new Float32Array(floats), indices: new Uint32Array(indices) };
}

/** En qué parte de su vida va la esfera, cuadro a cuadro. */
export interface ShellEnvelope {
  /** De 0 a 1: cuánto de la rejilla ya descubrió el frente de aparición. */
  reveal: number;
  /** Altura como tanto de la normal: 0 en el suelo, 1 arriba, más al expandirse. */
  lift: number;
  /** De 1 (encendida) a 0 (ya se disolvió). */
  fade: number;
  /** Destello del cierre, de 1 a 0. */
  flash: number;
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/**
 * Cómo se ve la esfera en el segundo `now`: aparece en {@link REVEAL_S} y,
 * desde `end`, destella, se expande y se disuelve en {@link DISSOLVE_S}.
 *
 * @param now Segundo actual (`performance.now() / 1000`).
 * @param start Segundo en que se puso la esfera.
 * @param end Segundo en que terminó la búsqueda, o `null` si sigue.
 * @param still Sin animación: todo encendido y quieto desde el principio.
 * @returns Aparición, altura, brillo y destello de ese cuadro.
 *
 * @example shellEnvelope(10.7, 10, null, false) // { reveal: 0.5, lift: 0.875, fade: 1, flash: 0 }
 */
export function shellEnvelope(
  now: number,
  start: number,
  end: number | null,
  still: boolean,
): ShellEnvelope {
  if (still) return { reveal: 1, lift: 1, fade: 1, flash: 0 };
  const reveal = clamp01((now - start) / REVEAL_S);
  const rise = easeOutCubic(reveal);
  if (end === null) return { reveal, lift: rise, fade: 1, flash: 0 };
  const k = clamp01((now - end) / DISSOLVE_S);
  return {
    reveal,
    lift: rise + (DISSOLVE_LIFT - 1) * easeOutCubic(k),
    // Suave al principio y al final (smoothstep).
    fade: 1 - k * k * (3 - 2 * k),
    flash: (1 - k) ** FLASH_POWER,
  };
}

/**
 * Distancia de la cámara al centro de la Tierra, en radios terrestres, a
 * partir del plano de recorte del globo que manda MapLibre: `[n, −1/D]`, con
 * `n` la dirección del centro a la cámara (vertical_perspective_transform.ts,
 * maplibre-gl 6.14.0). VERIFICAR al actualizar maplibre-gl.
 *
 * @param clippingPlane `defaultProjectionData.clippingPlane` del cuadro.
 * @returns La distancia en radios terrestres; infinita si el plano no la da.
 *
 * @example cameraDistance([0, 0, 1, -0.2]) // 5
 */
export function cameraDistance(clippingPlane: readonly number[]): number {
  const w = clippingPlane[3] ?? 0;
  return w < 0 ? -1 / w : Number.POSITIVE_INFINITY;
}

/**
 * Cuánto se ve la esfera según qué tan lejos está la cámara: de cerca se
 * apaga para no teñir toda la pantalla.
 *
 * @param distance Distancia de la cámara al centro de la Tierra, en radios
 *   terrestres (`cameraDistance`).
 * @returns De 0 (a {@link CAMERA_FADE_NEAR} o menos) a 1 (a {@link CAMERA_FADE_FAR} o más).
 */
export function cameraFade(distance: number): number {
  const k = clamp01((distance - CAMERA_FADE_NEAR) / (CAMERA_FADE_FAR - CAMERA_FADE_NEAR));
  return k * k * (3 - 2 * k);
}

/**
 * Brillo final: tenue, más bajo de día y apagado con la cámara muy cerca.
 *
 * @param daylight Si la Tierra está en modo día.
 * @param distance Distancia de la cámara en radios terrestres (`cameraDistance`).
 * @returns De 0 a {@link SHELL_INTENSITY}.
 */
export function shellIntensity(daylight: boolean, distance: number): number {
  return SHELL_INTENSITY * (daylight ? SHELL_DAY_SHARE : 1) * cameraFade(distance);
}

// Ritmo de las piezas que se mueven (ajustado a ojo con capturas, ADR-0116).
// Anillo de latitud: va y viene en ~7 s y llega hasta el 92 % del camino a
// cada polo (en los polos se vería como un punto).
const RING_SPEED_RAD_S = 0.9;
const RING_REACH = 0.46;
// Borde que «respira»: un ciclo cada ~3 s y baja hasta el 75 % de su brillo.
const BREATH_SPEED_RAD_S = 2.1;
const BREATH_DEPTH = 0.25;
// Ancho del frente de aparición, como tanto del camino de polo a polo.
const FRONT_WIDTH = 0.08;
// Los pings brillan más que el vidrio: si no, no se distinguían.
const PING_GAIN = 1.5;

// Pesos y ritmos del shader, ajustados a ojo con capturas (ADR-0116). Las
// curvas son campanas `exp(-(x · nitidez)²)`: más nitidez, línea más fina.
// Ping: destello al nacer que se apaga en ~1 s (e^-2.2 ≈ 11 %), un anillo
// nuevo cada ~2.2 s (0.45 por segundo), anillo fino (~1/10 del disco) y un
// núcleo que se apaga antes de la mitad del disco.
const PING_FLASH_DECAY = 2.2;
const PING_RING_RATE = 0.45;
const PING_RING_SHARPNESS = 10;
const PING_CORE_FALLOFF = 9;
// Cuánto aporta al ping cada pieza: anillo, núcleo y destello.
const PING_RING_WEIGHT = 0.55;
const PING_CORE_WEIGHT = 0.45;
const PING_FLASH_WEIGHT = 0.9;
// El núcleo y el destello tiran a blanco (mitad y mitad); lo demás es cian.
const PING_WHITE_SHARE = 0.5;
// Borde encendido: potencia de lo que el vidrio se ve de canto (3: solo la orilla).
const RIM_POWER = 3;
// Nitidez del frente de aparición, medida en anchos de frente (FRONT_WIDTH).
const FRONT_SHARPNESS = 1.5;
// Nitidez del anillo de latitud: ~1/40 del camino de polo a polo.
const WAVE_SHARPNESS = 40;
// Lo que suma cada pieza al vidrio: un fondo apenas visible, la rejilla, el
// borde, el haz y el anillo de latitud.
const GLASS_BASE = 0.035;
const GLASS_GRID = 0.22;
const GLASS_RIM = 0.4;
const GLASS_BEAM = 0.35;
const GLASS_WAVE = 0.22;
// El haz y el destello del cierre se ven a este tanto en la cara de la
// esfera y completos en la orilla (donde el vidrio se ve de canto).
const FACE_SHARE = 0.25;
// Brillo del frente de aparición mientras sube.
const FRONT_GLOW = 0.7;
// Con «Menos movimiento» los pings se dibujan como si fueran viejos (en
// segundos): su destello y sus anillos ya se calmaron.
const STILL_AGE_S = 100;
// Tope para no dividir entre cero si el plano de recorte no trae distancia.
const MIN_CLIP_W = 1e-4;

const VERTEX = `
in vec2 a_lnglat;
in vec3 a_utk;
in float a_birth;
in float a_seed;
uniform float u_time;
uniform float u_still;
uniform float u_lift;
out vec3 v_utk;
out float v_age;
out float v_seed;
out vec3 v_normal;
out vec3 v_view;
void main() {
  // Directo de longitud y latitud a la esfera unitaria del globo (y al norte,
  // longitud 0 en +z): Mercator no llega a los polos y dejaba huecos.
  vec2 r = radians(a_lnglat);
  vec3 dir = vec3(sin(r.x) * cos(r.y), sin(r.y), cos(r.x) * cos(r.y));
  vec3 elevated = dir * (1.0 + ${glslFloat(SHELL_ALTITUDE_SHARE)} * u_lift);
  vec4 position = u_projection_matrix * vec4(elevated, 1.0);
  // Lo que queda detrás de la Tierra cae fuera del recorte (como los arcos).
  position.z = globeComputeClippingZ(elevated) * position.w;
  gl_Position = position;
  // El plano de recorte es [dirección a la cámara, -1/distancia]: de ahí sale
  // dónde está la cámara, para encender el borde (VERIFICAR al actualizar
  // maplibre-gl).
  vec3 camera = u_projection_clipping_plane.xyz / max(-u_projection_clipping_plane.w, ${glslFloat(MIN_CLIP_W)});
  v_normal = dir;
  v_view = camera - elevated;
  v_utk = a_utk;
  v_age = u_still > 0.5 ? ${glslFloat(STILL_AGE_S)} : u_time - a_birth;
  v_seed = a_seed;
}`;

// El vidrio de la cúpula sobre toda la esfera: rejilla, borde encendido (con
// el ángulo de vista en lugar de la altura) y el haz, que aquí es un meridiano
// de luz. Mezcla aditiva (luz).
const FRAGMENT = `#version 300 es
precision highp float;
in vec3 v_utk;
in float v_age;
in float v_seed;
in vec3 v_normal;
in vec3 v_view;
uniform float u_time;
uniform float u_still;
uniform float u_intensity;
uniform float u_reveal;
uniform float u_fade;
uniform float u_flash;
out vec4 fragColor;
const float TAU = 6.2831853;${GLSL_GRID_LINE}
void main() {
  float u = v_utk.x;
  float t = v_utk.y;
  float kind = v_utk.z;
  vec3 cyan = vec3(0.0, 0.82, 1.0);
  vec3 white = vec3(0.85, 0.98, 1.0);
  float moving = 1.0 - u_still;
  if (kind > ${glslFloat(KIND_PING - 0.5)}) {
    // Ping: un núcleo encendido y un anillo que se abre una y otra vez, con
    // un destello al nacer.
    if (v_age < 0.0) discard;
    float flash = exp(-v_age * ${glslFloat(PING_FLASH_DECAY)});
    float phase = fract(v_age * ${glslFloat(PING_RING_RATE)} + v_seed);
    float ring = exp(-pow((t - phase) * ${glslFloat(PING_RING_SHARPNESS)}, 2.0)) * (1.0 - phase);
    float core = exp(-t * ${glslFloat(PING_CORE_FALLOFF)});
    float a = (${glslFloat(PING_RING_WEIGHT)} * ring + ${glslFloat(PING_CORE_WEIGHT)} * core
      + ${glslFloat(PING_FLASH_WEIGHT)} * flash * (1.0 - t))
      * u_intensity * ${glslFloat(PING_GAIN)} * u_fade;
    float whiten = ${glslFloat(PING_WHITE_SHARE)} * core + ${glslFloat(1 - PING_WHITE_SHARE)} * flash;
    fragColor = vec4(mix(cyan, white, clamp(whiten, 0.0, 1.0)) * a, a);
    return;
  }
  // Borde: el vidrio se ve de canto en la orilla de la esfera.
  float facing = abs(dot(normalize(v_normal), normalize(v_view)));
  float rim = pow(1.0 - facing, ${glslFloat(RIM_POWER)});
  // Aparición: un frente sube de sur a norte y deja la rejilla atrás.
  float front = u_reveal * (1.0 + 2.0 * ${glslFloat(FRONT_WIDTH)}) - ${glslFloat(FRONT_WIDTH)};
  float shown = 1.0 - smoothstep(front - ${glslFloat(FRONT_WIDTH)}, front, t);
  float edge = exp(-pow((t - front) / ${glslFloat(FRONT_WIDTH)} * ${glslFloat(FRONT_SHARPNESS)}, 2.0))
    * moving;
  // Haz: un meridiano de luz que le da la vuelta al planeta.
  float sweep = mod(u_time * ${glslFloat(BEAM_SPEED_RAD_S)}, TAU);
  float behind = mod(sweep - u * TAU + TAU, TAU);
  float beam = exp(-behind * ${glslFloat(BEAM_TAIL)}) * moving;
  // Anillo de latitud que va y viene de polo a polo (t = 0.5 es el ecuador).
  float ringT = 0.5 + ${glslFloat(RING_REACH)} * sin(u_time * ${glslFloat(RING_SPEED_RAD_S)});
  float wave = exp(-pow((t - ringT) * ${glslFloat(WAVE_SHARPNESS)}, 2.0)) * moving;
  // El borde «respira».
  float breath = 1.0 - ${glslFloat(BREATH_DEPTH)} * moving
    * (0.5 + 0.5 * sin(u_time * ${glslFloat(BREATH_SPEED_RAD_S)}));
  // La misma rejilla que la cúpula (gl.ts).
  float grid = max(line(u, ${glslFloat(GRID_MERIDIANS)}, ${glslFloat(GRID_MERIDIAN_WIDTH)}),
    line(t, ${glslFloat(GRID_PARALLELS)}, ${glslFloat(GRID_PARALLEL_WIDTH)}));
  float toRim = ${glslFloat(FACE_SHARE)} + ${glslFloat(1 - FACE_SHARE)} * rim;
  float glass = ${glslFloat(GLASS_BASE)} + ${glslFloat(GLASS_GRID)} * grid
    + ${glslFloat(GLASS_RIM)} * rim * breath
    + ${glslFloat(GLASS_BEAM)} * beam * toRim + ${glslFloat(GLASS_WAVE)} * wave;
  float a = ((glass * shown + ${glslFloat(FRONT_GLOW)} * edge) * u_fade + u_flash * toRim)
    * u_intensity;
  fragColor = vec4(cyan * a, a);
}`;

/** La capa de la esfera y sus pings. */
class WorldShellLayer implements CustomLayerInterface {
  readonly id = SHELL_LAYER;
  readonly type = 'custom' as const;
  readonly renderingMode = '3d' as const;
  private map: MapLibreMap | null = null;
  private program: WebGLProgram | null = null;
  private uniform: UniformLookup = () => null;
  private shell: GpuMesh | null = null;
  private pingGpu: GpuMesh | null = null;
  private pings: readonly Ping[] = [];
  // Los pings cambiaron y falta subirlos a la tarjeta de video.
  private pingsDirty = true;
  private failed = false;
  /** Segundo en que se puso y en que empezó a disolverse (`null`: sigue). */
  private readonly start = performance.now() / 1000;
  private end: number | null = null;
  /** Si se mueve (falso con «Menos movimiento»: quieta). */
  readonly animate: boolean;
  /** Modo día de la Tierra: brillo más bajo. */
  daylight: boolean;
  // Se avisa (fuera del cuadro) si la tarjeta de video no pudo con los shaders.
  private readonly onFailure: (() => void) | undefined;

  constructor(animate: boolean, daylight: boolean, onFailure?: () => void) {
    this.animate = animate;
    this.daylight = daylight;
    this.onFailure = onFailure;
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    this.shell = createMesh(gl);
    upload(gl, this.shell, shellMesh());
    this.pingGpu = createMesh(gl);
  }

  /** Cambia los pings encendidos (quien llama pide el cuadro). */
  setPings(pings: readonly Ping[]): void {
    this.pings = pings;
    // Se suben en el siguiente cuadro: tocar WebGL fuera de `render` le
    // movería a MapLibre el estado que tiene guardado.
    this.pingsDirty = true;
  }

  /** Empieza el cierre: destello, se expande y se disuelve (quien llama pide el cuadro). */
  beginDissolve(now: number): void {
    this.end ??= now;
  }

  private ensureProgram(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): WebGLProgram {
    if (this.program) return this.program;
    const program = buildProgram(gl, args, VERTEX, FRAGMENT);
    bindAttributes(gl, program, [this.shell, this.pingGpu], ATTRIBUTES, STRIDE);
    this.program = program;
    this.uniform = uniformLookup(gl, program);
    return program;
  }

  render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): void {
    if (!this.map || !this.shell || this.failed) return;
    const projection = args.defaultProjectionData;
    if (
      args.shaderData.variantName !== GLOBE_VARIANT ||
      projection.projectionTransition < GLOBE_ONLY_TRANSITION
    ) {
      return;
    }
    const now = performance.now() / 1000;
    const envelope = shellEnvelope(now, this.start, this.end, !this.animate);
    const intensity = shellIntensity(this.daylight, cameraDistance(projection.clippingPlane));
    // Ya se disolvió o la cámara está tan cerca que no se ve: nada que dibujar.
    if (intensity === 0 || (envelope.fade === 0 && envelope.flash === 0)) return;
    let program: WebGLProgram;
    try {
      program = this.ensureProgram(gl, args);
    } catch {
      // La tarjeta de video no pudo con los shaders: se deja de intentar y se
      // avisa fuera del cuadro (quien la puso muestra el radar plano).
      this.failed = true;
      setTimeout(() => this.onFailure?.(), 0);
      return;
    }
    if (this.pingsDirty && this.pingGpu) {
      upload(gl, this.pingGpu, pingMesh(this.pings));
      this.pingsDirty = false;
    }
    const uniform = this.uniform;
    gl.useProgram(program);
    setProjectionUniforms(gl, uniform, projection);
    gl.uniform1f(uniform('u_time'), this.animate ? now : 0);
    gl.uniform1f(uniform('u_still'), this.animate ? 0 : 1);
    gl.uniform1f(uniform('u_lift'), envelope.lift);
    gl.uniform1f(uniform('u_intensity'), intensity);
    gl.uniform1f(uniform('u_reveal'), envelope.reveal);
    gl.uniform1f(uniform('u_fade'), envelope.fade);
    gl.uniform1f(uniform('u_flash'), envelope.flash);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.DEPTH_TEST);
    gl.depthMask(false);
    for (const mesh of [this.shell, this.pingGpu]) {
      if (!mesh || mesh.count === 0) continue;
      gl.bindVertexArray(mesh.vao);
      gl.drawElements(gl.TRIANGLES, mesh.count, gl.UNSIGNED_INT, 0);
    }
    gl.bindVertexArray(null);
    // Mientras se mueve se pide el siguiente cuadro; quieta, nunca.
    if (this.animate) this.map.triggerRepaint();
  }

  onRemove(_map: MapLibreMap, gl: WebGL2RenderingContext): void {
    for (const mesh of [this.shell, this.pingGpu]) {
      if (mesh) deleteMesh(gl, mesh);
    }
    if (this.program) gl.deleteProgram(this.program);
    this.shell = null;
    this.pingGpu = null;
    this.program = null;
    this.uniform = () => null;
    this.map = null;
  }
}

/** Cómo actualizar, cerrar o quitar la esfera. */
export interface WorldShell {
  /** Enciende un ping por nota encontrada, hasta {@link SHELL_SPOTS}; los de atrás, al girar. */
  setBlips(count: number): void;
  /** Modo día de la Tierra: brillo más bajo. */
  setDaylight(daylight: boolean): void;
  /** Terminó la búsqueda: destella, se expande, se disuelve y se quita sola. */
  dissolve(): void;
  /** La quita en el acto. */
  remove(): void;
}

export interface WorldShellOptions {
  /** Si se mueve (falso con «Menos movimiento»). Por omisión, sí. */
  animate?: boolean;
  /** Si la Tierra está en modo día. */
  daylight?: boolean;
  /** Se llama (fuera del cuadro) si la tarjeta de video no pudo con la esfera. */
  onFailure?: () => void;
}

// La esfera puesta en cada mapa: un cierre tardío (el temporizador de una
// búsqueda anterior) no debe quitar la de la búsqueda nueva, que usa el mismo id.
const current = new WeakMap<MapLibreMap, WorldShellLayer>();

function detach(map: MapLibreMap, layer: WorldShellLayer): void {
  if (current.get(map) !== layer) return;
  current.delete(map);
  try {
    if (map.getLayer(SHELL_LAYER)) map.removeLayer(SHELL_LAYER);
  } catch {
    // El mapa ya se quitó o cambió de estilo: no queda capa que quitar.
  }
}

/**
 * Pone la esfera alrededor de la Tierra y devuelve cómo actualizarla.
 *
 * Si quedaba otra (una búsqueda anterior a medio disolverse), se quita antes.
 *
 * @param map Mapa ya cargado.
 * @param options Animación, modo día y aviso de falla.
 * @returns Cómo encender pings, cambiar el brillo, cerrarla o quitarla.
 * @throws {Error} Si el estilo del mapa todavía no carga (lo lanza MapLibre).
 *
 * @example
 *   const shell = addWorldShell(map, { animate: true });
 *   shell.setBlips(12);
 *   shell.dissolve(); // al terminar la búsqueda
 */
export function addWorldShell(map: MapLibreMap, options: WorldShellOptions = {}): WorldShell {
  const { animate = true, daylight = false, onFailure } = options;
  current.delete(map);
  if (map.getLayer(SHELL_LAYER)) map.removeLayer(SHELL_LAYER);
  const layer = new WorldShellLayer(animate, daylight, onFailure);
  map.addLayer(layer);
  current.set(map, layer);
  const spots = globeSpots();
  let wanted = 0;
  let pings: Ping[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;
  let removed = false;
  // Enciende los pings que faltan en los lugares que ya están al frente; lo
  // demás espera a que el giro los traiga (cada «move» de la cámara).
  const fill = () => {
    if (removed || pings.length >= wanted) return;
    const center = map.getCenter();
    const taken = new Set(pings.map((ping) => ping.point.join()));
    const fresh = spotsInView(spots, taken, [center.lng, center.lat], wanted - pings.length);
    if (fresh.length === 0) return;
    const now = performance.now() / 1000;
    // Escalonados, como los contactos de la cúpula: no se encienden de golpe.
    const offset = pings.length > 0 ? 1 : 0;
    pings = [
      ...pings,
      ...fresh.map((point, i) => ({
        point,
        birth: now + (i + offset) * CONTACT_STAGGER_S,
        seed: ((pings.length + i) * GOLDEN_FRACTION) % 1,
      })),
    ];
    layer.setPings(pings);
    map.triggerRepaint();
  };
  map.on('move', fill);
  const remove = () => {
    if (removed) return;
    removed = true;
    if (timer !== null) clearTimeout(timer);
    map.off('move', fill);
    detach(map, layer);
  };
  return {
    setBlips(count) {
      if (removed) return;
      // Uno por nota encontrada, hasta llenar los lugares del planeta. Los que
      // ya estaban no se mueven.
      wanted = Math.min(SHELL_SPOTS, Math.max(0, count));
      fill();
    },
    setDaylight(day) {
      layer.daylight = day;
      map.triggerRepaint();
    },
    dissolve() {
      if (removed || timer !== null) return;
      if (!animate) {
        remove();
        return;
      }
      layer.beginDissolve(performance.now() / 1000);
      map.triggerRepaint();
      // Se quita fuera del cuadro (nunca dentro de `render`).
      timer = setTimeout(remove, DISSOLVE_S * 1000 + DISSOLVE_MARGIN_MS);
    },
    remove,
  };
}
