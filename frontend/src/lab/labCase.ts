/**
 * Casos de prueba del laboratorio del muro (Fase 9.1, ADR-0102).
 *
 * Sirven para medir el motor visual antes de que existan casos reales (9.2+):
 * - un caso pequeño con la forma del caso de Polanco (víctima, señalado,
 *   detenidos, la fiscalía, los lugares de sus negocios), **sin nombres
 *   reales**: es una herramienta que perfila personas y el repositorio no
 *   guarda datos personales de prueba;
 * - casos sintéticos de N nodos repartidos en ciudades de México.
 *
 * También la geometría de los arcos (gran círculo con altura), la misma para
 * las dos opciones que se comparan, para que la medición sea justa.
 *
 * No hace: no dibuja ni consulta la API; son datos y cálculos puros.
 */
import { seededRandom } from '../map/space';

export type NodeKind = 'person' | 'place' | 'org' | 'vehicle';
/** Estatus legal tal como lo diría la nota (plan §9.2); nunca "culpable". */
export type LegalStatus = 'mencionado' | 'señalado' | 'detenido' | 'víctima' | 'testigo';

export interface LabNode {
  id: string;
  kind: NodeKind;
  label: string;
  legal: LegalStatus | null;
  lng: number;
  lat: number;
}

export interface LabLink {
  id: string;
  from: string;
  to: string;
  /** Confirmado por un humano; los sugeridos se dibujan punteados. */
  confirmed: boolean;
  /** 0..1: grosor y brillo del arco. */
  confidence: number;
}

export interface LabCase {
  name: string;
  nodes: LabNode[];
  links: LabLink[];
}

/** Colores por tipo de entidad (plan §9.5: "color por tipo"). */
export const KIND_COLOR: Record<NodeKind, string> = {
  person: '#38BDF8',
  place: '#34D399',
  org: '#FBBF24',
  vehicle: '#A78BFA',
};

/** Borde por estatus legal (plan §9.5: "borde rojo = señalado, azul = víctima"). */
export const LEGAL_COLOR: Record<LegalStatus, string> = {
  mencionado: '#E2E8F0',
  señalado: '#F87171',
  detenido: '#FB923C',
  víctima: '#60A5FA',
  testigo: '#E2E8F0',
};

// Forma del caso de Polanco (búsquedas reales del 20/10/2026), sin nombres.
export const DEMO_CASE: LabCase = {
  name: 'Caso de prueba: homicidio en Polanco',
  nodes: [
    {
      id: 'v',
      kind: 'person',
      label: 'Víctima (estilista)',
      legal: 'víctima',
      lng: -99.1966,
      lat: 19.434,
    },
    { id: 's', kind: 'person', label: 'Empresario', legal: 'señalado', lng: -99.199, lat: 19.432 },
    {
      id: 'd',
      kind: 'person',
      label: 'Tres detenidos',
      legal: 'detenido',
      lng: -99.015,
      lat: 19.4,
    },
    { id: 'polanco', kind: 'place', label: 'Polanco', legal: null, lng: -99.1966, lat: 19.434 },
    {
      id: 'zapopan',
      kind: 'place',
      label: 'Puerta de Hierro, Zapopan',
      legal: null,
      lng: -103.413,
      lat: 20.705,
    },
    {
      id: 'neza',
      kind: 'place',
      label: 'Nezahualcóyotl',
      legal: null,
      lng: -99.0146,
      lat: 19.4006,
    },
    { id: 'cancun', kind: 'place', label: 'Cancún', legal: null, lng: -86.8515, lat: 21.1619 },
    {
      id: 'fiscalia',
      kind: 'org',
      label: 'Fiscalía de la CDMX',
      legal: null,
      lng: -99.155,
      lat: 19.427,
    },
    { id: 'moto', kind: 'vehicle', label: 'Motocicleta', legal: null, lng: -99.192, lat: 19.437 },
  ],
  links: [
    { id: 'v-s', from: 'v', to: 's', confirmed: true, confidence: 0.9 },
    { id: 'v-polanco', from: 'v', to: 'polanco', confirmed: true, confidence: 0.95 },
    { id: 's-polanco', from: 's', to: 'polanco', confirmed: true, confidence: 0.8 },
    { id: 'd-neza', from: 'd', to: 'neza', confirmed: true, confidence: 0.7 },
    { id: 'd-v', from: 'd', to: 'v', confirmed: true, confidence: 0.85 },
    { id: 'v-zapopan', from: 'v', to: 'zapopan', confirmed: false, confidence: 0.5 },
    { id: 's-cancun', from: 's', to: 'cancun', confirmed: false, confidence: 0.4 },
    { id: 'fiscalia-s', from: 'fiscalia', to: 's', confirmed: true, confidence: 0.75 },
    { id: 'moto-d', from: 'moto', to: 'd', confirmed: false, confidence: 0.45 },
  ],
};

// Ciudades donde se agrupan los nodos sintéticos: así hay arcos cortos (misma
// ciudad) y largos (entre estados), como en un caso real.
const CITIES: [number, number][] = [
  [-99.13, 19.43],
  [-103.35, 20.67],
  [-100.31, 25.69],
  [-98.2, 19.04],
  [-89.62, 20.97],
  [-86.85, 21.16],
  [-106.42, 31.69],
  [-117.04, 32.53],
  [-96.72, 17.06],
  [-102.29, 21.88],
  [-110.31, 24.14],
  [-93.12, 16.75],
];
const KINDS: NodeKind[] = ['person', 'person', 'person', 'place', 'org', 'vehicle'];
const LEGALS: LegalStatus[] = ['mencionado', 'señalado', 'detenido', 'víctima'];
// ~0.15° de dispersión dentro de una ciudad (unos 15 km).
const CITY_SPREAD_DEGREES = 0.15;
// 1.5 vínculos por nodo: lo que se vio en el caso de Polanco (9 nodos, 9 arcos)
// más margen para casos densos.
const LINKS_PER_NODE = 1.5;
// Proporción de vínculos entre ciudades distintas (arcos largos).
const LONG_LINK_SHARE = 0.25;

/**
 * Caso sintético de `size` nodos, siempre igual para la misma semilla.
 *
 * @param size Número de nodos.
 * @param seed Semilla (la misma semilla da el mismo caso: mediciones repetibles).
 * @returns Nodos repartidos en ciudades de México y ~1.5 vínculos por nodo.
 */
export function syntheticCase(size: number, seed = 91): LabCase {
  const random = seededRandom(seed);
  const pick = <T>(items: readonly T[]): T => items[Math.floor(random() * items.length)] as T;
  const nodes: LabNode[] = [];
  const cityOf: number[] = [];
  for (let i = 0; i < size; i += 1) {
    const city = Math.floor(random() * CITIES.length);
    const [lng, lat] = CITIES[city] ?? CITIES[0] ?? [-99.13, 19.43];
    const kind = pick(KINDS);
    nodes.push({
      id: `n${String(i)}`,
      kind,
      label: `Entidad ${String(i + 1)}`,
      legal: kind === 'person' ? pick(LEGALS) : null,
      lng: lng + (random() - 0.5) * 2 * CITY_SPREAD_DEGREES,
      lat: lat + (random() - 0.5) * 2 * CITY_SPREAD_DEGREES,
    });
    cityOf.push(city);
  }
  const links: LabLink[] = [];
  const total = Math.round(size * LINKS_PER_NODE);
  for (let i = 0; i < total && size > 1; i += 1) {
    const a = Math.floor(random() * size);
    const long = random() < LONG_LINK_SHARE;
    let b = Math.floor(random() * size);
    for (let tries = 0; tries < 20 && (b === a || (!long && cityOf[b] !== cityOf[a])); tries += 1) {
      b = Math.floor(random() * size);
    }
    if (b === a) continue;
    links.push({
      id: `l${String(i)}`,
      from: `n${String(a)}`,
      to: `n${String(b)}`,
      confirmed: random() > 0.3,
      confidence: 0.4 + random() * 0.6,
    });
  }
  return { name: `Caso sintético de ${String(size)} nodos`, nodes, links };
}

const DEGREES = Math.PI / 180;
const EARTH_RADIUS_M = 6_371_008.8;
// Altura del arco: una fracción de su largo, con piso (que un arco dentro de
// Polanco se vea levantado) y techo (que CDMX–Cancún no salga del cuadro).
export const ARC_HEIGHT_SHARE = 0.22;
export const ARC_MIN_HEIGHT_M = 1_500;
export const ARC_MAX_HEIGHT_M = 700_000;

type Vec3 = [number, number, number];

function toVector(lng: number, lat: number): Vec3 {
  const phi = lat * DEGREES;
  const lambda = lng * DEGREES;
  return [Math.cos(phi) * Math.cos(lambda), Math.cos(phi) * Math.sin(lambda), Math.sin(phi)];
}

/** Distancia sobre la Tierra en metros (gran círculo). */
export function greatCircleMeters(a: [number, number], b: [number, number]): number {
  const [ax, ay, az] = toVector(a[0], a[1]);
  const [bx, by, bz] = toVector(b[0], b[1]);
  const dot = Math.min(1, Math.max(-1, ax * bx + ay * by + az * bz));
  return Math.acos(dot) * EARTH_RADIUS_M;
}

/** Altura máxima del arco entre dos puntos, en metros. */
export function arcHeightMeters(distanceMeters: number): number {
  return Math.min(ARC_MAX_HEIGHT_M, Math.max(ARC_MIN_HEIGHT_M, distanceMeters * ARC_HEIGHT_SHARE));
}

/**
 * Puntos del arco de luz entre dos lugares: sigue el gran círculo y se eleva
 * como una parábola (seno), más alto cuanto más lejos.
 *
 * @param a Origen [lng, lat].
 * @param b Destino [lng, lat].
 * @param samples Puntos del arco (incluye los extremos); más puntos, arco más suave.
 * @returns `[lng, lat, alturaEnMetros]` de cada punto.
 */
export function arcPath(
  a: [number, number],
  b: [number, number],
  samples: number,
): [number, number, number][] {
  const va = toVector(a[0], a[1]);
  const vb = toVector(b[0], b[1]);
  const dot = Math.min(1, Math.max(-1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2]));
  const omega = Math.acos(dot);
  const height = arcHeightMeters(omega * EARTH_RADIUS_M);
  const points: [number, number, number][] = [];
  const count = Math.max(2, samples);
  for (let i = 0; i < count; i += 1) {
    const t = i / (count - 1);
    // Interpolación esférica (slerp); si los puntos casi coinciden, lineal.
    const [wa, wb] =
      omega < 1e-9
        ? [1 - t, t]
        : [Math.sin((1 - t) * omega) / Math.sin(omega), Math.sin(t * omega) / Math.sin(omega)];
    const x = wa * va[0] + wb * vb[0];
    const y = wa * va[1] + wb * vb[1];
    const z = wa * va[2] + wb * vb[2];
    const lat = Math.atan2(z, Math.hypot(x, y)) / DEGREES;
    const lng = Math.atan2(y, x) / DEGREES;
    points.push([lng, lat, height * Math.sin(Math.PI * t)]);
  }
  return points;
}

/** Nodos por id, para unir los vínculos con sus extremos. */
export function nodesById(labCase: LabCase): Map<string, LabNode> {
  return new Map(labCase.nodes.map((node) => [node.id, node]));
}
