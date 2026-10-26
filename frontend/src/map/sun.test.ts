/** El Sol en su posición real (rediseño del globo, 26/10/2026). */
import { describe, expect, it } from 'vitest';

import { LIGHT_RADIUS, subsolarPoint, sunLightPosition, sunSkyDirection } from './sun';

describe('subsolarPoint', () => {
  it('en el solsticio de junio está sobre el trópico de Cáncer, a mediodía en Greenwich', () => {
    const point = subsolarPoint(new Date('2026-06-21T12:00:00Z'));
    expect(point.lat).toBeCloseTo(23.44, 0);
    expect(Math.abs(point.lng)).toBeLessThan(2);
  });

  it('el 26 de octubre a las 18:00 UTC está al sur del ecuador, sobre las Américas', () => {
    const point = subsolarPoint(new Date('2026-10-26T18:00:00Z'));
    expect(point.lat).toBeLessThan(-11);
    expect(point.lat).toBeGreaterThan(-14);
    // Mediodía solar ~4 h antes que el reloj de Greenwich: ~94° O.
    expect(point.lng).toBeLessThan(-90);
    expect(point.lng).toBeGreaterThan(-98);
  });
});

describe('sunLightPosition', () => {
  it('el Sol sobre (0°, 0°) está justo «encima» (polar 0)', () => {
    const [radius, , polar] = sunLightPosition({ lat: 0, lng: 0 });
    expect(radius).toBe(LIGHT_RADIUS);
    expect(polar).toBeCloseTo(0);
  });

  it('el Sol sobre el polo norte está al norte, a 90° de (0°, 0°)', () => {
    const [, azimuth, polar] = sunLightPosition({ lat: 90, lng: 0 });
    expect(azimuth).toBeCloseTo(0);
    expect(polar).toBeCloseTo(90);
  });

  it('del otro lado del mundo queda detrás (polar 180)', () => {
    expect(sunLightPosition({ lat: 0, lng: 180 })[2]).toBeCloseTo(180);
  });
});

describe('sunSkyDirection', () => {
  it('usa el marco de las estrellas: Z al (0°, 0°), X al este, Y al norte', () => {
    expect(sunSkyDirection({ lat: 0, lng: 0 }).z).toBeCloseTo(1);
    expect(sunSkyDirection({ lat: 0, lng: 90 }).x).toBeCloseTo(1);
    expect(sunSkyDirection({ lat: 90, lng: 0 }).y).toBeCloseTo(1);
  });
});
