/** Línea del tiempo (F12.7): momento de cada nota, tramos, picos y filtros. */
import { describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import {
  mapLead,
  applyTimeline,
  buildTimeline,
  categoriesIn,
  chronological,
  NO_FILTERS,
  noteMoment,
  platformFacet,
  stateCodeOf,
  statesIn,
  storyItems,
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

  it('varias categorías a la vez: las notas de cualquiera de ellas (28/10/2026)', () => {
    const picked = applyTimeline(notes, { ...NO_FILTERS, categoryIds: [6, 7] });
    expect(new Set(picked.map((a) => a.category?.id))).toEqual(new Set([6, 7]));
    expect(applyTimeline(notes, { ...NO_FILTERS, categoryIds: [] })).toHaveLength(notes.length);
  });

  it('el estado sale de la clave INEGI de la ubicación principal', () => {
    expect(notes.map(stateCodeOf)).toEqual(['08', '19', '08', null]);
  });

  it('filtra por tramo, categoría y estado a la vez', () => {
    expect(applyTimeline(notes, NO_FILTERS).map((a) => a.article_id)).toEqual([1, 2, 3, 4]);
    expect(
      applyTimeline(notes, { ...NO_FILTERS, categoryIds: [6] }).map((a) => a.article_id),
    ).toEqual([2, 3]);
    expect(
      applyTimeline(notes, { range: null, categoryIds: [6], stateCode: '08', platforms: [] }).map(
        (a) => a.article_id,
      ),
    ).toEqual([3]);
    const range = [Date.parse('2026-10-25T21:00:00Z'), Date.parse('2026-10-25T22:00:00Z')] as const;
    expect(applyTimeline(notes, { ...NO_FILTERS, range }).map((a) => a.article_id)).toEqual([1]);
  });

  it('filtra por plataforma (ADR-0117); sin el dato, la nota cuenta como noticia', () => {
    const mixed = [
      ...notes,
      note(5, '2026-10-26T03:00:00Z', { platform: 'facebook', category: ARMAS }),
      note(6, '2026-10-26T04:00:00Z', { platform: 'x' }),
      note(7, '2026-10-26T05:00:00Z', { platform: 'news' }),
    ];
    const ids = (filters: Partial<typeof NO_FILTERS>) =>
      applyTimeline(mixed, { ...NO_FILTERS, ...filters }).map((a) => a.article_id);

    expect(ids({ platforms: ['facebook'] })).toEqual([5]);
    expect(ids({ platforms: ['facebook', 'x'] })).toEqual([5, 6]);
    // Las notas 1 a 4 no traen plataforma (respuestas de antes): son noticias.
    expect(ids({ platforms: ['news'] })).toEqual([1, 2, 3, 4, 7]);
    // Se combina con los demás filtros.
    expect(ids({ platforms: ['facebook'], categoryIds: [7] })).toEqual([]);
    expect(ids({ platforms: ['facebook'], categoryIds: [6] })).toEqual([5]);
    expect(ids({ platforms: [] })).toHaveLength(mixed.length);
  });

  it('el conteo de plataformas es facetado: bajan con la categoría y la ubicación (revisión del 18/11/2026)', () => {
    const mixed = [
      ...notes,
      { ...note(5, '2026-10-26T03:00:00Z', { platform: 'facebook', category: ARMAS }) },
      { ...note(6, '2026-10-26T04:00:00Z', { platform: 'facebook' }), in_region: false },
      { ...note(7, '2026-10-26T05:00:00Z', { platform: 'x', category: ARMAS }), in_region: null },
    ];
    const count = (facet: Article[], platform: string) =>
      facet.filter((a) => (a.platform ?? 'news') === platform).length;
    const all = platformFacet(mixed, {
      filters: { range: null, categoryIds: [], stateCode: null },
      listFilter: 'all',
    });
    expect([count(all, 'news'), count(all, 'facebook'), count(all, 'x')]).toEqual([4, 2, 1]);

    // Con una categoría: Facebook baja de 2 a 1 y coincide con lo que se vería.
    const armas = platformFacet(mixed, {
      filters: { range: null, categoryIds: [6], stateCode: null },
      listFilter: 'all',
    });
    expect([count(armas, 'news'), count(armas, 'facebook'), count(armas, 'x')]).toEqual([2, 1, 1]);
    const facebookArmas = applyTimeline(mixed, {
      ...NO_FILTERS,
      categoryIds: [6],
      platforms: ['facebook'],
    });
    expect(count(armas, 'facebook')).toBe(facebookArmas.length);

    // Con «Dentro de zona»: se van la de fuera y la sin lugar.
    const inside = platformFacet(mixed, {
      filters: { range: null, categoryIds: [], stateCode: null },
      listFilter: 'true',
    });
    expect([count(inside, 'news'), count(inside, 'facebook'), count(inside, 'x')]).toEqual([
      4, 1, 0,
    ]);
  });

  it('cuenta estados y categorías de más a menos', () => {
    expect(statesIn(notes)).toEqual([
      { code: '08', name: 'Chihuahua', count: 2 },
      { code: '19', name: 'Nuevo León', count: 1 },
    ]);
    expect(categoriesIn(notes)).toEqual([
      { id: 6, name: 'Armas y explosivos', color: null, count: 2 },
      { id: 7, name: 'Huachicol y delitos contra hidrocarburos', color: null, count: 1 },
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

describe('storyItems', () => {
  it('un hecho en varios medios es una sola entrada, de la más reciente a la más vieja', () => {
    const notes = [
      note(1, '2026-10-25T21:10:00Z', { story_id: 1 }),
      note(2, '2026-10-25T21:30:00Z', { story_id: 1 }),
      note(3, '2026-10-26T05:40:00Z'),
      note(4, null),
    ];

    const items = storyItems(notes);

    expect(items.map((i) => [i.lead.article_id, i.articleIds, i.day])).toEqual([
      // 05:40 UTC del 26 son las 23:40 del 25 en la CDMX.
      [3, [3], '2026-10-25'],
      [1, [1, 2], '2026-10-25'],
    ]);
  });
});

describe('mapLead', () => {
  it('vuela a la nota del hecho mejor ubicada, aunque no sea la primera', () => {
    const lead = note(1, '2026-10-27T10:00:00Z');
    const state = note(2, '2026-10-27T11:00:00Z', { regionCode: '29' });
    const town = note(3, '2026-10-27T12:00:00Z', { regionCode: '29001' });
    if (state.primary_location) state.primary_location.precision = 'state';
    expect(mapLead({ lead, notes: [lead, state, town] }).article_id).toBe(3);
  });

  it('sin ninguna ubicada, se queda con la principal', () => {
    const lead = note(1, '2026-10-27T10:00:00Z');
    const other = note(2, '2026-10-27T11:00:00Z');
    expect(mapLead({ lead, notes: [lead, other] })).toBe(lead);
  });
});
