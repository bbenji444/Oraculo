/**
 * Plomería WebGL 2 que comparten las capas del radar: la cúpula de una región
 * (dome.ts) y la esfera de «Todo el mundo» (shell.ts, ADR-0116).
 *
 * - compila y enlaza el programa con el preludio de proyección que da
 *   MapLibre a las capas propias;
 * - sube mallas (vértices intercalados e índices) a la tarjeta de video y las
 *   borra;
 * - pone los uniforms de la proyección del globo, guardando las ubicaciones
 *   para no pedirlas en cada cuadro.
 *
 * No hace: no sabe qué se dibuja ni cómo se ve; eso lo decide cada capa.
 */
import type { CustomRenderMethodInput } from 'maplibre-gl';

/** Vértices intercalados e índices de triángulos. */
export interface Mesh {
  floats: Float32Array;
  indices: Uint32Array;
}

/** Una malla en la tarjeta de video: su VAO, sus búferes y cuántos índices tiene. */
export interface GpuMesh {
  vao: WebGLVertexArrayObject;
  vbo: WebGLBuffer;
  ibo: WebGLBuffer;
  count: number;
}

/** Atributo de vértice: nombre en el shader, cuántos números y desde cuál. */
export type Attribute = readonly [name: string, size: number, offset: number];

/** Datos de proyección que MapLibre le pasa a una capa propia en cada cuadro. */
export type ProjectionData = CustomRenderMethodInput['defaultProjectionData'];

/** Devuelve la ubicación de un uniform del programa (o `null` si no se usa). */
export type UniformLookup = (name: string) => WebGLUniformLocation | null;

// Bytes por número de la malla (Float32).
const FLOAT_BYTES = 4;

/**
 * La función `line()` de la rejilla en GLSL: 1 sobre la línea y 0 lejos de
 * ella, con orilla suave. La usan la cúpula y la esfera para que su rejilla
 * se vea igual.
 */
export const GLSL_GRID_LINE = `
float line(float value, float count, float width) {
  float d = abs(fract(value * count + 0.5) - 0.5);
  return 1.0 - smoothstep(0.0, width, d);
}`;

/**
 * Rejilla del vidrio, igual en la cúpula y en la esfera: 12 meridianos (uno
 * cada 30°) y 6 paralelos, con un grosor de 4 % y 5 % del espacio entre
 * líneas. Elegida a ojo con capturas de la cúpula (diseño del 11/11/2026) y
 * reusada en la esfera para que se vean del mismo material (ADR-0116).
 */
export const GRID_MERIDIANS = 12;
export const GRID_PARALLELS = 6;
export const GRID_MERIDIAN_WIDTH = 0.04;
export const GRID_PARALLEL_WIDTH = 0.05;

/**
 * Un número de TypeScript escrito como flotante de GLSL: GLSL no acepta `2`
 * donde espera `float`, hay que escribir `2.0`.
 *
 * @example glslFloat(2) // '2.0'; glslFloat(0.06) // '0.06'
 */
export function glslFloat(value: number): string {
  return Number.isInteger(value) ? value.toFixed(1) : String(value);
}

/**
 * Compila un shader.
 *
 * @param gl Contexto WebGL 2 del mapa.
 * @param type `gl.VERTEX_SHADER` o `gl.FRAGMENT_SHADER`.
 * @param source Código GLSL completo.
 * @returns El shader compilado.
 * @throws {Error} Si WebGL no lo crea o no compila (lleva el registro del compilador).
 */
export function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error('WebGL no pudo crear el shader del radar.');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(`Shader del radar: ${gl.getShaderInfoLog(shader) ?? 'error'}`);
  }
  return shader;
}

/**
 * Arma el programa de una capa propia: al shader de vértices le antepone el
 * preludio de proyección que manda MapLibre (cambia entre globo y plano).
 *
 * @param gl Contexto WebGL 2 del mapa.
 * @param args Lo que MapLibre pasa a `render` (trae el preludio y su `#define`).
 * @param vertexBody Cuerpo del shader de vértices, sin `#version`.
 * @param fragment Shader de fragmentos completo, con su `#version 300 es`.
 * @returns El programa enlazado.
 * @throws {Error} Si un shader no compila o el programa no enlaza.
 */
export function buildProgram(
  gl: WebGL2RenderingContext,
  args: CustomRenderMethodInput,
  vertexBody: string,
  fragment: string,
): WebGLProgram {
  const { shaderData } = args;
  const vertex = `#version 300 es\n${shaderData.vertexShaderPrelude}\n${shaderData.define}\n${vertexBody}`;
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, vertex));
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragment));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(`Programa del radar: ${gl.getProgramInfoLog(program) ?? 'error'}`);
  }
  return program;
}

/** Crea una malla vacía en la tarjeta de video (se llena con {@link upload}). */
export function createMesh(gl: WebGL2RenderingContext): GpuMesh {
  const vao = gl.createVertexArray();
  const vbo = gl.createBuffer();
  const ibo = gl.createBuffer();
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo);
  gl.bindVertexArray(null);
  return { vao, vbo, ibo, count: 0 };
}

/** Sube (o reemplaza) los vértices e índices de una malla. */
export function upload(gl: WebGL2RenderingContext, target: GpuMesh, mesh: Mesh): void {
  gl.bindBuffer(gl.ARRAY_BUFFER, target.vbo);
  gl.bufferData(gl.ARRAY_BUFFER, mesh.floats, gl.STATIC_DRAW);
  gl.bindVertexArray(target.vao);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, gl.STATIC_DRAW);
  gl.bindVertexArray(null);
  target.count = mesh.indices.length;
}

/** Libera la malla de la tarjeta de video. */
export function deleteMesh(gl: WebGL2RenderingContext, mesh: GpuMesh): void {
  gl.deleteVertexArray(mesh.vao);
  gl.deleteBuffer(mesh.vbo);
  gl.deleteBuffer(mesh.ibo);
}

/**
 * Conecta los atributos del programa con los búferes de cada malla.
 *
 * @param gl Contexto WebGL 2 del mapa.
 * @param program Programa recién enlazado.
 * @param meshes Mallas que se dibujan con ese programa (las nulas se saltan).
 * @param attributes Nombre, tamaño y posición de cada atributo en el vértice.
 * @param stride Números por vértice.
 */
export function bindAttributes(
  gl: WebGL2RenderingContext,
  program: WebGLProgram,
  meshes: readonly (GpuMesh | null)[],
  attributes: readonly Attribute[],
  stride: number,
): void {
  for (const mesh of meshes) {
    if (!mesh) continue;
    gl.bindVertexArray(mesh.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, mesh.vbo);
    for (const [name, size, offset] of attributes) {
      const location = gl.getAttribLocation(program, name);
      if (location >= 0) {
        gl.enableVertexAttribArray(location);
        gl.vertexAttribPointer(
          location,
          size,
          gl.FLOAT,
          false,
          stride * FLOAT_BYTES,
          offset * FLOAT_BYTES,
        );
      }
    }
  }
  gl.bindVertexArray(null);
}

/**
 * Ubicaciones de los uniforms de un programa, pedidas una sola vez: antes se
 * pedían a WebGL en cada cuadro (decenas de llamadas por cuadro).
 *
 * @example const uniform = uniformLookup(gl, program); gl.uniform1f(uniform('u_time'), 1);
 */
export function uniformLookup(gl: WebGL2RenderingContext, program: WebGLProgram): UniformLookup {
  const cache = new Map<string, WebGLUniformLocation | null>();
  return (name) => {
    if (!cache.has(name)) cache.set(name, gl.getUniformLocation(program, name));
    return cache.get(name) ?? null;
  };
}

/**
 * Pone los uniforms del preludio de proyección de MapLibre (globo o plano).
 *
 * @param gl Contexto WebGL 2 del mapa, con el programa ya en uso.
 * @param uniform Ubicaciones del programa ({@link uniformLookup}).
 * @param projection `args.defaultProjectionData` del cuadro.
 */
export function setProjectionUniforms(
  gl: WebGL2RenderingContext,
  uniform: UniformLookup,
  projection: ProjectionData,
): void {
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
}
