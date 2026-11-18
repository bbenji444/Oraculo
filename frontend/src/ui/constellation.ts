/**
 * Cálculos de la constelación del fondo de Oráculo core (ADR-0108): puntos
 * cian que derivan despacio, líneas tenues entre los que están cerca y halos
 * grandes que laten. Los valores son los de `static/js/constellation.js` de
 * Oráculo (leído del servidor el 17/11/2026).
 *
 * Aquí solo se crean, se mueven y se unen los puntos, para poder probarlo. Los
 * dibuja `components/Space/Constellation.tsx`.
 *
 * No hace: no toca el lienzo ni decide cuándo se anima.
 */

/** Cuántos puntos (Oráculo: `particleCount`). */
export const PARTICLE_COUNT = 60;
/** Distancia, en px, a la que dos puntos se unen con una línea (`connectionDistance`). */
export const CONNECTION_DISTANCE = 150;
/** Cuántos halos (`haloCount`). */
export const HALO_COUNT = 5;
/** Cuánto crece y se encoge cada halo al latir, en px (`Math.sin(...) * 20`). */
export const HALO_PULSE_PX = 20;

/** Colores de Oráculo: puntos, líneas y halos. */
export const STAR_COLOR = 'rgba(0, 210, 255, 0.5)';
export const LINE_COLOR = 'rgba(0, 210, 255, 0.15)';
export const HALO_COLOR = 'rgba(0, 210, 255, 0.05)';

// Velocidad de deriva de los puntos: hasta ±0.15 px por cuadro (`particleSpeed`
// 0.3 por un aleatorio centrado en cero). Los cuadros son los de 60 por segundo
// de Oráculo; aquí se dibuja a menos y se avanza en proporción.
const PARTICLE_SPEED = 0.3;
// Radio de los puntos: de 1 a 3 px (`Math.random() * 2 + 1`).
const PARTICLE_MIN_SIZE = 1;
const PARTICLE_SIZE_RANGE = 2;
// Halos: hasta ±0.05 px por cuadro, radio de 50 a 150 px y latido de 0.02 rad
// por cuadro.
const HALO_SPEED = 0.1;
const HALO_MIN_SIZE = 50;
const HALO_SIZE_RANGE = 100;
const HALO_PULSE_SPEED = 0.02;

export interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
}

export interface Halo {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  /** Fase del latido, en radianes. */
  pulse: number;
}

/** Línea entre dos puntos cercanos; más delgada mientras más lejos estén. */
export interface Link {
  from: Particle;
  to: Particle;
  width: number;
}

type Random = () => number;

/** Un aleatorio centrado en cero, de -0.5 a 0.5. */
function centered(random: Random): number {
  return random() - 0.5;
}

/**
 * Reparte los puntos al azar en el área.
 *
 * @param width Ancho del área, en px.
 * @param height Alto del área, en px.
 * @param random Fuente de aleatorios (las pruebas pasan una fija).
 * @returns PARTICLE_COUNT puntos con posición, velocidad y tamaño.
 */
export function makeParticles(
  width: number,
  height: number,
  random: Random = Math.random,
): Particle[] {
  return Array.from({ length: PARTICLE_COUNT }, () => ({
    x: random() * width,
    y: random() * height,
    vx: centered(random) * PARTICLE_SPEED,
    vy: centered(random) * PARTICLE_SPEED,
    size: random() * PARTICLE_SIZE_RANGE + PARTICLE_MIN_SIZE,
  }));
}

/**
 * Reparte los halos al azar en el área.
 *
 * @param width Ancho del área, en px.
 * @param height Alto del área, en px.
 * @param random Fuente de aleatorios.
 * @returns HALO_COUNT halos con posición, velocidad, tamaño y fase del latido.
 */
export function makeHalos(width: number, height: number, random: Random = Math.random): Halo[] {
  return Array.from({ length: HALO_COUNT }, () => ({
    x: random() * width,
    y: random() * height,
    vx: centered(random) * HALO_SPEED,
    vy: centered(random) * HALO_SPEED,
    size: random() * HALO_SIZE_RANGE + HALO_MIN_SIZE,
    pulse: random() * Math.PI,
  }));
}

/**
 * Avanza un punto y lo hace rebotar en las orillas, como en Oráculo.
 *
 * @param particle El punto; se modifica en su lugar (se mueven decenas por cuadro).
 * @param width Ancho del área, en px.
 * @param height Alto del área, en px.
 * @param steps Cuántos cuadros de 60 por segundo avanza.
 */
export function stepParticle(
  particle: Particle,
  width: number,
  height: number,
  steps: number,
): void {
  particle.x += particle.vx * steps;
  particle.y += particle.vy * steps;
  if (particle.x < 0 || particle.x > width) particle.vx *= -1;
  if (particle.y < 0 || particle.y > height) particle.vy *= -1;
}

/**
 * Avanza un halo y su latido; al salir por una orilla entra por la contraria.
 *
 * @param halo El halo; se modifica en su lugar.
 * @param width Ancho del área, en px.
 * @param height Alto del área, en px.
 * @param steps Cuántos cuadros de 60 por segundo avanza.
 */
export function stepHalo(halo: Halo, width: number, height: number, steps: number): void {
  halo.x += halo.vx * steps;
  halo.y += halo.vy * steps;
  halo.pulse += HALO_PULSE_SPEED * steps;
  if (halo.x < -halo.size) halo.x = width + halo.size;
  if (halo.x > width + halo.size) halo.x = -halo.size;
  if (halo.y < -halo.size) halo.y = height + halo.size;
  if (halo.y > height + halo.size) halo.y = -halo.size;
}

/** El radio del halo en este momento de su latido, en px. */
export function haloRadius(halo: Halo): number {
  return halo.size + Math.sin(halo.pulse) * HALO_PULSE_PX;
}

/**
 * Las líneas entre los puntos que están a menos de CONNECTION_DISTANCE.
 *
 * @param particles Los puntos.
 * @returns Una línea por cada par cercano, con grosor de 1 px (juntos) a 0 (en
 *   el límite), como en Oráculo.
 */
export function linksBetween(particles: readonly Particle[]): Link[] {
  const links: Link[] = [];
  for (const [i, from] of particles.entries()) {
    for (const to of particles.slice(i + 1)) {
      const distance = Math.hypot(from.x - to.x, from.y - to.y);
      if (distance < CONNECTION_DISTANCE) {
        links.push({ from, to, width: 1 - distance / CONNECTION_DISTANCE });
      }
    }
  }
  return links;
}
