/**
 * Texto de los shaders de la cúpula (dome.ts) y de la esfera (shell.ts).
 *
 * No hay WebGL en las pruebas: un contexto de juguete guarda el código que
 * cada capa manda a compilar, y aquí se revisa ese texto: que la cúpula y la
 * esfera giren igual y tengan la misma rejilla (ADR-0116), y que todo número
 * esté escrito como flotante de GLSL (con `2` en lugar de `2.0` no compila).
 */
import type { CustomRenderMethodInput, Map as MapLibreMap } from 'maplibre-gl';
import { describe, expect, it, vi } from 'vitest';

import { addDomeRadar, BEAM_SPEED_RAD_S, BEAM_TAIL } from './dome';
import {
  glslFloat,
  GRID_MERIDIAN_WIDTH,
  GRID_MERIDIANS,
  GRID_PARALLEL_WIDTH,
  GRID_PARALLELS,
} from './gl';
import { addWorldShell } from './shell';

interface Captured {
  vertex: string;
  fragment: string;
}

// Constantes de WebGL que distingue el contexto de juguete.
const VERTEX_SHADER = 0x8b31;
const FRAGMENT_SHADER = 0x8b30;

/**
 * Contexto WebGL 2 de juguete: todo lo que no se define aquí es una función
 * que no hace nada; guarda el código de cada shader que se compila.
 */
function toyGl(): { gl: WebGL2RenderingContext; sources: Map<number, string> } {
  const sources = new Map<number, string>();
  const types = new Map<object, number>();
  const known: Record<string, unknown> = {
    VERTEX_SHADER,
    FRAGMENT_SHADER,
    createShader: (type: number) => {
      const shader = {};
      types.set(shader, type);
      return shader;
    },
    shaderSource: (shader: object, source: string) => {
      sources.set(types.get(shader) ?? -1, source);
    },
    getShaderParameter: () => true,
    getProgramParameter: () => true,
    getAttribLocation: () => -1,
    getUniformLocation: () => null,
    createProgram: () => ({}),
    createVertexArray: () => ({}),
    createBuffer: () => ({}),
  };
  const gl = new Proxy(
    {},
    {
      get: (_target, name: string) => (name in known ? known[name] : () => undefined),
    },
  ) as WebGL2RenderingContext;
  return { gl, sources };
}

/** Lo que MapLibre pasa a `render` con el globo puro y la cámara a 5 radios. */
const GLOBE_FRAME = {
  shaderData: { variantName: 'globe', vertexShaderPrelude: '', define: '#define GLOBE' },
  defaultProjectionData: {
    mainMatrix: new Array<number>(16).fill(0),
    tileMercatorCoords: [0, 0, 1, 1],
    clippingPlane: [0, 0, 1, -0.2],
    projectionTransition: 1,
    fallbackMatrix: new Array<number>(16).fill(0),
  },
} as unknown as CustomRenderMethodInput;

/** Mapa de juguete que guarda la capa que se le agrega. */
function toyMap() {
  const layers: { onAdd: (...a: unknown[]) => void; render: (...a: unknown[]) => void }[] = [];
  const map = {
    addLayer: vi.fn((layer: (typeof layers)[number]) => {
      layers.push(layer);
    }),
    getLayer: vi.fn(() => undefined),
    removeLayer: vi.fn(),
    triggerRepaint: vi.fn(),
    getCenter: vi.fn(() => ({ lng: -35, lat: 20 })),
  };
  return { asMap: map as unknown as MapLibreMap, layers };
}

/** Pone la capa en el mapa de juguete, dibuja un cuadro y devuelve sus shaders. */
function captureShaders(add: (map: MapLibreMap) => unknown): Captured {
  const { asMap, layers } = toyMap();
  add(asMap);
  const [layer] = layers;
  if (!layer) throw new Error('La capa no se agregó al mapa.');
  const { gl, sources } = toyGl();
  layer.onAdd(asMap, gl);
  layer.render(gl, GLOBE_FRAME);
  return {
    vertex: sources.get(VERTEX_SHADER) ?? '',
    fragment: sources.get(FRAGMENT_SHADER) ?? '',
  };
}

const dome = () => captureShaders((map) => addDomeRadar(map, [-105.7, 18.9, -101.5, 22.75]));
const shell = () => captureShaders((map) => addWorldShell(map, { animate: true }));

/** Los grupos de `pattern` en el texto; falla si no aparece. */
function read(source: string, pattern: RegExp): string[] {
  const match = pattern.exec(source);
  if (!match) throw new Error(`No aparece ${String(pattern)} en el shader.`);
  return match.slice(1);
}

const SWEEP = /mod\(u_time \* ([\d.]+), TAU\)/;
const TAIL = /exp\(-behind \* ([\d.]+)\)/;
const MERIDIANS = /line\(u, ([\d.]+), ([\d.]+)\)/;

/** Números enteros sueltos (sin punto): GLSL no los acepta donde espera float. */
function bareIntegers(source: string): string[] {
  const code = source
    .replace(/\/\/.*$/gm, '')
    .replace(/#version \d+ es/, '')
    .replace(/#define \w+/g, '');
  return code.match(/(?<![\w.])\d+(?![\w.])/g) ?? [];
}

describe('shaders del radar', () => {
  it('la cúpula y la esfera giran al mismo ritmo, con la misma estela', () => {
    const d = dome().fragment;
    const s = shell().fragment;

    expect(read(d, SWEEP)).toEqual([glslFloat(BEAM_SPEED_RAD_S)]);
    expect(read(s, SWEEP)).toEqual([glslFloat(BEAM_SPEED_RAD_S)]);
    expect(read(d, TAIL)).toEqual([glslFloat(BEAM_TAIL)]);
    expect(read(s, TAIL)).toEqual([glslFloat(BEAM_TAIL)]);
  });

  it('las dos usan la rejilla de gl.ts', () => {
    const expected = [glslFloat(GRID_MERIDIANS), glslFloat(GRID_MERIDIAN_WIDTH)];
    expect(read(dome().fragment, MERIDIANS)).toEqual(expected);
    expect(read(shell().fragment, MERIDIANS)).toEqual(expected);
    expect(shell().fragment).toContain(
      `line(t, ${glslFloat(GRID_PARALLELS)}, ${glslFloat(GRID_PARALLEL_WIDTH)})`,
    );
  });

  it('todos los números van escritos como flotantes de GLSL', () => {
    for (const { vertex, fragment } of [dome(), shell()]) {
      expect(bareIntegers(vertex)).toEqual([]);
      expect(bareIntegers(fragment)).toEqual([]);
    }
  });
});
