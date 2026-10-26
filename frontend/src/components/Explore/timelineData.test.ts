/** Línea del tiempo (F12.7): momento de cada nota, tramos, picos y filtros. */
import { describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import {
  applyTimeline,
  buildTimeline,
  categoriesIn,
  chronological,
  NO_FILTERS,
  noteMoment,
  stateCodeOf,
  statesIn,
} from './timelineData';

const HUACHICOL = {
  id: 7,
  name: 'Huachicol y delitos contra hidrocarburos',
  color: null,
  symbol: null,
};
const ARMAS = { id: 6, name: 'Armas y explosivos', color: null, symbol: null };

function note(
  id: number,
  publishedAt: string | null,
  extra: Partial<Article> & { regionCode?: string } = {},
): Article {
  const { regionCode, ...rest } = extra;
  return {
    article_id: id,
    title: `Nota ${String(id)}`,
    source_name: null,
    source_domain: null,
    url: `https://medio.mx/${String(id)}`,
    published_at: publishedAt,
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts: [],
    primary_location: regionCode
      ? {
          mention: 'x',
          role: 'event',
          precision: 'municipality',
          confidence: 1,
          is_primary: true,
          region_id: 1,
          region_code: regionCode,
          place: null,
          lon: 0,
          lat: 0,
        }
      : null,
    in_region: true,
    providers: [],
    ...rest,
  };
}

describe('noteMoment', () => {
  it('manda la fecha del hecho; sin ella, la de publicación', () => {
    const old = note(1, '2026-10-25T18:00:00Z', { event_date: '2025-09-29' });
    expect(noteMoment(old)).toEqual({ at: Date.parse('2025-09-29T18:00:00Z'), kind: 'event' });
    expect(noteMoment(note(2, '2026-10-25T18:00:00Z'))).toEqual({
      at: Date.parse('2026-10-25T18:00:00Z'),
      kind: 'published',
    });
    expect(noteMoment(note(3, null))).toBeNull();
  });
});

describe('buildTimeline', () => {
  it('en menos de 3 días corta por hora de la CDMX, con los huecos y los picos', () => {
    // 15:10 y 15:50 CDMX = 21:10 y 21:50 UTC; 17:05 CDMX = 23:05 UTC.
    const timeline = buildTimeline([
      note(1, '2026-10-25T21:10:00Z'),
      note(2, '2026-10-25T21:50:00Z'),
      note(3, '2026-10-25T23:05:00Z'),
      note(4, null),
    ]);

    expect(timeline.unit).toBe('hour');
    expect(timeline.buckets.map((b) => b.articleIds)).toEqual([[1, 2], [], [3]]);
    // El tramo empieza a las 15:00 en punto de la CDMX.
    expect(timeline.buckets[0]?.start).toBe(Date.parse('2026-10-25T21:00:00Z'));
    expect(timeline.max).toBe(2);
    expect(timeline.undated).toBe(1);
    expect(timeline.buckets.map((b) => b.peak)).toEqual([true, false, true]);
  });

  it('con más de 3 días corta por día de la CDMX', () => {
    // 23:30 del 20 en la CDMX es el 21 a las 05:30 UTC: cuenta para el día 20.
    const timeline = buildTimeline([
      note(1, '2026-10-21T05:30:00Z'),
      note(2, '2026-10-25T18:00:00Z'),
    ]);

    expect(timeline.unit).toBe('day');
    expect(timeline.buckets).toHaveLength(6);
    expect(timeline.buckets[0]?.start).toBe(Date.parse('2026-10-20T06:00:00Z'));
  });

  it('sin notas con fecha no hay tramos', () => {
    expect(buildTimeline([note(1, null)])).toEqual({
      unit: 'hour',
      buckets: [],
      max: 0,
      undated: 1,
    });
  });
});

describe('filtros', () => {
  const notes = [
    note(1, '2026-10-25T21:10:00Z', { category: HUACHICOL, regionCode: '08019' }),
    note(2, '2026-10-25T23:00:00Z', { category: ARMAS, regionCode: '19039' }),
    note(3, '2026-10-26T01:00:00Z', { category: ARMAS, regionCode: '08' }),
    note(4, '2026-10-26T02:00:00Z', { regionCode: 'MEX' }),
  ];

  it('el estado sale de la clave INEGI de la ubicación principal', () => {
    expect(notes.map(stateCodeOf)).toEqual(['08', '19', '08', null]);
  });

  it('filtra por tramo, categoría y estado a la vez', () => {
    expect(applyTimeline(notes, NO_FILTERS).map((a) => a.article_id)).toEqual([1, 2, 3, 4]);
    expect(applyTimeline(notes, { ...NO_FILTERS, categoryId: 6 }).map((a) => a.article_id)).toEqual(
      [2, 3],
    );
    expect(
      applyTimeline(notes, { range: null, categoryId: 6, stateCode: '08' }).map(
        (a) => a.article_id,
      ),
    ).toEqual([3]);
    const range = [Date.parse('2026-10-25T21:00:00Z'), Date.parse('2026-10-25T22:00:00Z')] as const;
    expect(applyTimeline(notes, { ...NO_FILTERS, range }).map((a) => a.article_id)).toEqual([1]);
  });

  it('cuenta estados y categorías de más a menos', () => {
    expect(statesIn(notes)).toEqual([
      { code: '08', name: 'Chihuahua', count: 2 },
      { code: '19', name: 'Nuevo León', count: 1 },
    ]);
    expect(categoriesIn(notes)).toEqual([
      { id: 6, name: 'Armas y explosivos', count: 2 },
      { id: 7, name: 'Huachicol y delitos contra hidrocarburos', count: 1 },
    ]);
  });

  it('el orden cronológico deja al final las notas sin fecha', () => {
    expect(chronological([note(9, null), ...notes].reverse()).map((a) => a.article_id)).toEqual([
      1, 2, 3, 4, 9,
    ]);
  });

  it('por defecto ordena por la fecha del hecho; también por publicación', () => {
    // La 5 se publicó al final, pero el hecho es de 2025: va primero.
    const old = note(5, '2026-10-26T03:00:00Z', { event_date: '2025-09-29' });
    expect(chronological([...notes, old]).map((a) => a.article_id)).toEqual([5, 1, 2, 3, 4]);
    expect(chronological([...notes, old], 'published').map((a) => a.article_id)).toEqual([
      1, 2, 3, 4, 5,
    ]);
  });

  it('las barras usan la publicación: un hecho viejo no estira el eje', () => {
    const old = note(5, '2026-10-25T21:30:00Z', { event_date: '2025-09-29' });
    const timeline = buildTimeline([note(1, '2026-10-25T21:10:00Z'), old]);
    expect(timeline.unit).toBe('hour');
    expect(timeline.buckets.map((b) => b.articleIds)).toEqual([[1, 5]]);
  });
});
