/** Cálculos de las animaciones: contador, descifrado, mini gráfica y luz del mouse. */
import { describe, expect, it } from 'vitest';

import { countAt, DECODE_GLYPHS, decodeAt, easeOutExpo } from './motion';
import { sparklinePoints } from './sparkline';
import { pointIn } from './spotlight';

describe('easeOutExpo', () => {
  it('empieza en 0, termina en 1 y no se sale de ese rango', () => {
    expect(easeOutExpo(-1)).toBe(0);
    expect(easeOutExpo(0)).toBe(0);
    expect(easeOutExpo(1)).toBe(1);
    expect(easeOutExpo(2)).toBe(1);
    // Arranca rápido: a la mitad ya recorrió casi todo.
    expect(easeOutExpo(0.5)).toBeGreaterThan(0.95);
  });
});

describe('countAt', () => {
  it('corre del valor anterior al nuevo', () => {
    expect(countAt(0, 175, 0)).toBe(0);
    expect(countAt(0, 175, 1)).toBe(175);
    expect(countAt(175, 33, 1)).toBe(33);
    const mid = countAt(0, 175, 0.3);
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(175);
  });
});

describe('decodeAt', () => {
  const zero = () => 0;

  it('al final es el texto real y al inicio solo relleno', () => {
    expect(decodeAt('CASOS', 1, zero)).toBe('CASOS');
    expect(decodeAt('CASOS', 0, zero)).toBe('AAAAA');
  });

  it('revela de izquierda a derecha y respeta espacios y puntuación', () => {
    // 18 caracteres: a la mitad ya se ven los 9 primeros («ESTADO DE»).
    expect(decodeAt('ESTADO DEL SISTEMA', 0.5, zero)).toBe('ESTADO DEA AAAAAAA');
    expect(decodeAt('23:00 · FGR', 0, zero)).toBe('AA:AA · AAA');
  });

  it('los acentos y la Ñ también se descifran', () => {
    expect(decodeAt('AÑO', 0, zero)).toBe('AAA');
    expect(decodeAt('AÑO', 1, zero)).toBe('AÑO');
  });

  it('el relleno sale de los caracteres de terminal', () => {
    const glyphs = new Set(DECODE_GLYPHS);
    for (const char of decodeAt('MONITOR', 0)) expect(glyphs.has(char)).toBe(true);
  });
});

describe('sparklinePoints', () => {
  it('reparte los puntos a lo ancho, con margen para no cortar el trazo', () => {
    expect(sparklinePoints([0, 5, 10], 100, 20)).toEqual([
      [3, 17],
      [50, 10],
      [97, 3],
    ]);
  });

  it('una serie plana queda a media altura… o abajo, sin dividir entre cero', () => {
    const points = sparklinePoints([4, 4], 100, 20);
    expect(points.every(([, y]) => Number.isFinite(y))).toBe(true);
  });

  it('sin valores no hay puntos', () => {
    expect(sparklinePoints([], 100, 20)).toEqual([]);
  });
});

describe('pointIn', () => {
  it('da la posición del mouse dentro del elemento', () => {
    expect(pointIn({ left: 100, top: 40 }, 160, 95)).toEqual({ x: 60, y: 55 });
  });
});
