/**
 * Opción A del ADR-0102: el muro con MapLibre puro, sin dependencias nuevas.
 *
 * - **Arcos de luz:** una capa propia (`CustomLayerInterface`, modo 3D) que
 *   dibuja cada arco como una cinta en pantalla, levantada sobre el globo con
 *   `projectTileWithElevation` (la función del preludio de MapLibre que además
 *   recorta lo que queda detrás del horizonte). El brillo es un halo aditivo en
 *   el shader y un pulso de luz recorre cada arco. Los sugeridos van punteados.
 * - **Nodos:** dos capas de círculo de MapLibre: halo difuso que late y núcleo
 *   con borde del color del estatus legal.
 *
 * API del preludio verificada en `maplibre-gl@6.14.0` instalado
 * (`CustomRenderMethodInput.shaderData` y `defaultProjectionData`).
 *
 * No hace: no mueve la cámara (eso es `labScript.ts`).
 */
import {
  type CustomLayerInterface,
  type CustomRenderMethodInput,
  type Map as MapLibreMap,
  MercatorCoordinate,
} from 'maplibre-gl';

import { arcPath, type LabCase, nodesById } from './labCase';
import { addNodeLabels, MURO_SOURCE, type MuroEngine, removeNodeSource } from './muroLabels';

const ARCS_LAYER = 'muro-arcs';
const HALO_LAYER = 'muro-node-halo';
const CORE_LAYER = 'muro-node-core';
// Puntos por arco: 48 bastan para que CDMX–Cancún se vea curvo y no se corte
// en el horizonte (la documentación de MapLibre pide subdividir).
const ARC_SAMPLES = 48;
// Ancho de la cinta en píxeles CSS: el núcleo ocupa el centro y el resto es halo.
const RIBBON_WIDTH_PX = 14;
// El halo de los nodos late a 30 cuadros por segundo: suficiente y barato.
const PULSE_FRAME_MS = 1000 / 30;
const ARC_CONFIRMED_COLOR: [number, number, number] = [0.49, 0.83, 0.99];
const ARC_SUGGESTED_COLOR: [number, number, number] = [0.8, 0.84, 0.9];

const VERTEX = `
in vec2 a_pos;
in vec2 a_prev;
in vec2 a_next;
in vec3 a_elev;
in vec2 a_side_t;
in vec4 a_color;
in vec2 a_meta;
uniform vec2 u_viewport;
uniform float u_width;
out float v_side;
out float v_t;
out vec4 v_color;
out vec2 v_meta;
void main() {
  vec4 cur = projectTileWithElevation(a_pos, a_elev.x);
  vec4 prev = projectTileWithElevation(a_prev, a_elev.y);
  vec4 next = projectTileWithElevation(a_next, a_elev.z);
  vec2 sp = prev.xy / prev.w * u_viewport;
  vec2 sn = next.xy / next.w * u_viewport;
  vec2 dir = normalize(sn - sp + vec2(1e-6, 0.0));
  vec2 normal = vec2(-dir.y, dir.x);
  cur.xy += normal * a_side_t.x * u_width / u_viewport * cur.w;
  gl_Position = cur;
  v_side = a_side_t.x;
  v_t = a_side_t.y;
  v_color = a_color;
  v_meta = a_meta;
}`;

const FRAGMENT = `#version 300 es
precision highp float;
in float v_side;
in float v_t;
in vec4 v_color;
in vec2 v_meta;
uniform float u_time;
out vec4 fragColor;
void main() {
  float d = abs(v_side);
  float core = 1.0 - smoothstep(0.0, 0.2, d);
  float halo = exp(-d * d * 6.0) * 0.4;
  float travel = fract(u_time * 0.22 + v_meta.x);
  float pulse = exp(-pow((v_t - travel) * 16.0, 2.0));
  float dash = v_meta.y > 0.5 ? 1.0 : step(0.45, fract(v_t * 22.0));
  float a = (core * (0.45 + 0.55 * v_color.a) + halo * v_color.a + pulse * (core + halo)) * dash;
  fragColor = vec4(v_color.rgb * a, a);
}`;

interface ArcBuffers {
  vao: WebGLVertexArrayObject;
  buffers: WebGLBuffer[];
  indexCount: number;
}

/** Geometría de cintas: 2 vértices por punto del arco (un lado y el otro). */
export function arcRibbons(labCase: LabCase, samples = ARC_SAMPLES) {
  const byId = nodesById(labCase);
  const floats: number[] = [];
  const indices: number[] = [];
  let vertex = 0;
  labCase.links.forEach((link, linkIndex) => {
    const a = byId.get(link.from);
    const b = byId.get(link.to);
    if (!a || !b) return;
    const path = arcPath([a.lng, a.lat], [b.lng, b.lat], samples).map(([lng, lat, h]) => {
      const m = MercatorCoordinate.fromLngLat([lng, lat]);
      return [m.x, m.y, h] as const;
    });
    const color = link.confirmed ? ARC_CONFIRMED_COLOR : ARC_SUGGESTED_COLOR;
    // Fase del pulso distinta por arco: no laten todos al mismo tiempo.
    const phase = (linkIndex * 0.618) % 1;
    path.forEach((point, i) => {
      const prev = path[Math.max(0, i - 1)] ?? point;
      const next = path[Math.min(path.length - 1, i + 1)] ?? point;
      for (const side of [-1, 1]) {
        floats.push(
          point[0],
          point[1],
          prev[0],
          prev[1],
          next[0],
          next[1],
          point[2],
          prev[2],
          next[2],
          side,
          i / (path.length - 1),
          ...color,
          link.confidence,
          phase,
          link.confirmed ? 1 : 0,
        );
      }
      if (i < path.length - 1) {
        const base = vertex + i * 2;
        indices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2);
      }
    });
    vertex += path.length * 2;
  });
  return { floats: new Float32Array(floats), indices: new Uint32Array(indices) };
}

// Atributos por vértice en el arreglo intercalado (nombre, componentes).
const ATTRIBUTES: [string, number][] = [
  ['a_pos', 2],
  ['a_prev', 2],
  ['a_next', 2],
  ['a_elev', 3],
  ['a_side_t', 2],
  ['a_color', 4],
  ['a_meta', 2],
];
const STRIDE_FLOATS = ATTRIBUTES.reduce((sum, [, size]) => sum + size, 0);

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error('WebGL no pudo crear el shader de arcos.');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(`Shader de arcos: ${gl.getShaderInfoLog(shader) ?? 'error'}`);
  }
  return shader;
}

/** Capa propia de arcos de luz (opción A). */
class ArcGlowLayer implements CustomLayerInterface {
  readonly id = ARCS_LAYER;
  readonly type = 'custom' as const;
  readonly renderingMode = '3d' as const;
  private map: MapLibreMap | null = null;
  private program: WebGLProgram | null = null;
  private programKey = '';
  private geometry: ArcBuffers | null = null;
  private readonly labCase: LabCase;

  constructor(labCase: LabCase) {
    this.labCase = labCase;
  }

  onAdd(map: MapLibreMap, gl: WebGL2RenderingContext): void {
    this.map = map;
    const { floats, indices } = arcRibbons(this.labCase);
    const vao = gl.createVertexArray();
    const vbo = gl.createBuffer();
    const ibo = gl.createBuffer();
    gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, floats, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
    gl.bindVertexArray(null);
    this.geometry = { vao, buffers: [vbo, ibo], indexCount: indices.length };
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
      throw new Error(`Programa de arcos: ${gl.getProgramInfoLog(program) ?? 'error'}`);
    }
    // Los atributos se enlazan una vez por programa en el VAO.
    if (this.geometry) {
      gl.bindVertexArray(this.geometry.vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.geometry.buffers[0] ?? null);
      let offset = 0;
      for (const [name, size] of ATTRIBUTES) {
        const location = gl.getAttribLocation(program, name);
        if (location >= 0) {
          gl.enableVertexAttribArray(location);
          gl.vertexAttribPointer(location, size, gl.FLOAT, false, STRIDE_FLOATS * 4, offset * 4);
        }
        offset += size;
      }
      gl.bindVertexArray(null);
    }
    this.program = program;
    this.programKey = shaderData.variantName;
    return program;
  }

  render(gl: WebGL2RenderingContext, args: CustomRenderMethodInput): void {
    const geometry = this.geometry;
    if (!geometry || !this.map) return;
    const program = this.ensureProgram(gl, args);
    const projection = args.defaultProjectionData;
    const uniform = (name: string) => gl.getUniformLocation(program, name);
    gl.useProgram(program);
    // La matriz puede venir en doble precisión; WebGL pide Float32.
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
    const canvas = this.map.getCanvas();
    gl.uniform2f(uniform('u_viewport'), canvas.width, canvas.height);
    gl.uniform1f(uniform('u_width'), RIBBON_WIDTH_PX * this.map.getPixelRatio());
    gl.uniform1f(uniform('u_time'), performance.now() / 1000);
    gl.enable(gl.BLEND);
    // Mezcla aditiva: el brillo suma luz sobre el mapa oscuro.
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.DEPTH_TEST);
    gl.depthMask(false);
    gl.bindVertexArray(geometry.vao);
    gl.drawElements(gl.TRIANGLES, geometry.indexCount, gl.UNSIGNED_INT, 0);
    gl.bindVertexArray(null);
    // El pulso de luz recorre los arcos: se pide el siguiente cuadro.
    this.map.triggerRepaint();
  }

  onRemove(_map: MapLibreMap, gl: WebGL2RenderingContext): void {
    if (this.geometry) {
      gl.deleteVertexArray(this.geometry.vao);
      for (const buffer of this.geometry.buffers) gl.deleteBuffer(buffer);
    }
    if (this.program) gl.deleteProgram(this.program);
    this.geometry = null;
    this.program = null;
    this.map = null;
  }
}

/**
 * Dibuja el caso con la opción A.
 *
 * @param map Mapa ya cargado.
 * @param labCase Caso a dibujar.
 * @returns Cómo quitarlo.
 */
export function addMapLibreMuro(map: MapLibreMap, labCase: LabCase): MuroEngine {
  addNodeLabels(map, labCase);
  map.addLayer(new ArcGlowLayer(labCase));
  map.addLayer({
    id: HALO_LAYER,
    type: 'circle',
    source: MURO_SOURCE,
    paint: {
      'circle-radius': 16,
      'circle-color': ['get', 'color'],
      'circle-blur': 1,
      'circle-opacity': 0.55,
    },
  });
  map.addLayer({
    id: CORE_LAYER,
    type: 'circle',
    source: MURO_SOURCE,
    paint: {
      'circle-radius': 5.5,
      'circle-color': ['get', 'color'],
      'circle-stroke-width': 2,
      'circle-stroke-color': ['get', 'ring'],
    },
  });
  let frame = 0;
  let last = 0;
  const pulse = (now: number) => {
    frame = requestAnimationFrame(pulse);
    if (now - last < PULSE_FRAME_MS) return;
    last = now;
    map.setPaintProperty(HALO_LAYER, 'circle-radius', 14 + 5 * Math.sin(now / 450));
  };
  frame = requestAnimationFrame(pulse);
  return {
    remove: () => {
      cancelAnimationFrame(frame);
      removeNodeSource(map, [ARCS_LAYER, HALO_LAYER, CORE_LAYER]);
    },
  };
}
