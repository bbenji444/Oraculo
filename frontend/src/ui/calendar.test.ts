import { describe, expect, it } from 'vitest';

import {
  addDays,
  GRID_DAYS,
  isIsoDate,
  longDate,
  monthGrid,
  monthOf,
  monthTitle,
  outOfBounds,
  shiftMonth,
  shortDate,
  todayInMexico,
} from './calendar';

describe('cuadrícula del mes', () => {
  it('octubre de 2026 empieza el lunes 28 de septiembre y siempre trae 6 semanas', () => {
    const grid = monthGrid({ year: 2026, month: 9 });

    expect(grid).toHaveLength(GRID_DAYS);
    expect(grid[0]).toEqual({ iso: '2026-09-28', day: 28, inMonth: false });
    expect(grid.find((d) => d.iso === '2026-10-28')?.inMonth).toBe(true);
    expect(grid.at(-1)?.iso).toBe('2026-11-08');
  });

  it('un mes que empieza en lunes no repite la semana anterior', () => {
    // 1 de junio de 2026 es lunes.
    expect(monthGrid({ year: 2026, month: 5 })[0]?.iso).toBe('2026-06-01');
  });
});

describe('moverse por las fechas', () => {
  it('cambia de mes y de año', () => {
    expect(shiftMonth({ year: 2026, month: 11 }, 1)).toEqual({ year: 2027, month: 0 });
    expect(shiftMonth({ year: 2026, month: 0 }, -1)).toEqual({ year: 2025, month: 11 });
  });

  it('suma días sin saltarse ninguno con el cambio de horario', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2026-03-08', 7)).toBe('2026-03-15');
  });

  it('respeta los límites', () => {
    expect(outOfBounds('2026-10-29', undefined, '2026-10-28')).toBe(true);
    expect(outOfBounds('2026-10-01', '2026-10-05')).toBe(true);
    expect(outOfBounds('2026-10-10', '2026-10-05', '2026-10-28')).toBe(false);
  });
});

describe('cómo se lee', () => {
  it('escribe las fechas en español', () => {
    expect(shortDate('2026-10-28')).toBe('28/10/2026');
    expect(longDate('2026-10-28')).toBe('28 de octubre de 2026');
    expect(monthTitle(monthOf('2026-10-28'))).toBe('octubre de 2026');
  });

  it('reconoce fechas válidas', () => {
    expect(isIsoDate('2026-02-29')).toBe(false);
    expect(isIsoDate('2026-10-28')).toBe(true);
    expect(isIsoDate(undefined)).toBe(false);
  });

  it('hoy es el día de la Ciudad de México, no el de UTC', () => {
    // 28/10/2026 a las 23:30 en CDMX ya es 29 en UTC.
    expect(todayInMexico(new Date('2026-10-29T05:30:00Z'))).toBe('2026-10-28');
  });
});
