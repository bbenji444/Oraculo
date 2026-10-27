/**
 * Cálculos de las animaciones de texto y cifras (27/10/2026).
 *
 * Funciones puras (sin DOM) para el contador que sube hasta su valor
 * (`CountUp`) y el texto que se «descifra» letra por letra (`DecodeText`).
 * Así se prueban sin navegador.
 *
 * No hace: no programa cuadros ni toca el DOM.
 */

/** Caracteres de relleno mientras el texto se descifra: aire de terminal. */
export const DECODE_GLYPHS = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&*+<>/';

/** Duración del contador, en milisegundos. */
export const COUNT_UP_MS = 900;
/** Duración del descifrado, en milisegundos. */
export const DECODE_MS = 420;

/** Curva que arranca rápido y frena suave (como la de hud.css). */
export function easeOutExpo(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return 1 - 2 ** (-10 * t);
}

/**
 * Valor del contador en un momento de su animación.
 *
 * @param from Valor inicial.
 * @param to Valor final.
 * @param t Avance de 0 a 1.
 * @example countAt(0, 175, 1) // 175
 */
export function countAt(from: number, to: number, t: number): number {
  return from + (to - from) * easeOutExpo(t);
}

/**
 * Texto a medio descifrar: las primeras letras ya son las reales; el resto,
 * caracteres al azar. Los espacios y la puntuación no se tocan.
 *
 * @param text Texto final.
 * @param t Avance de 0 a 1.
 * @param random Fuente de azar (0 a 1), para poder probarla.
 * @example decodeAt('CASOS', 1, Math.random) // 'CASOS'
 */
export function decodeAt(text: string, t: number, random: () => number = Math.random): string {
  const revealed = Math.floor(text.length * Math.min(Math.max(t, 0), 1));
  return Array.from(text, (char, index) => {
    if (index < revealed || !/[\p{L}\p{N}]/u.test(char)) return char;
    return DECODE_GLYPHS.charAt(Math.floor(random() * DECODE_GLYPHS.length));
  }).join('');
}

/** Si la persona pidió al sistema reducir las animaciones. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}
