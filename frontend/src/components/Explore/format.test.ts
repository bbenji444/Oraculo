import { describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import {
  conceptSlices,
  formatDay,
  formatMexicoCity,
  formatUsd,
  isCoarse,
  NO_CONCEPT_COLOR,
  stageProgress,
} from './format';

function article(judgements: [number, string, boolean][]): Article {
  return {
    article_id: 1,
    title: 'Nota',
    source_name: null,
    source_domain: null,
    url: 'https://x.mx',
    published_at: null,
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts: judgements.map(([id, name, relevant]) => ({
      concept_id: id,
      name,
      is_relevant: relevant,
      relevance_score: 1,
      relevance_reason: null,
    })),
    primary_location: null,
    in_region: null,
    providers: [],
  };
}

describe('fechas en hora de la Ciudad de México', () => {
  it('convierte desde UTC', () => {
    expect(formatMexicoCity('2026-10-17T15:00:48Z')).toBe('17/10/2026, 09:00');
    expect(formatDay('2026-10-17T03:00:00Z')).toBe('16 oct');
  });
});

describe('avance de una búsqueda', () => {
  it('cada etapa suma y la IA avanza por notas resumidas', () => {
    expect(stageProgress({ stage: 'query' }, 'running')).toEqual({
      label: 'Consultando proveedores',
      percent: 13,
    });
    expect(stageProgress({ stage: 'enrich', articles: 20, enriched: 10 }, 'running').percent).toBe(
      56,
    );
    // Notas ya procesadas antes no cuentan como pendientes.
    expect(
      stageProgress({ stage: 'enrich', articles: 20, reused: 10, enriched: 10 }, 'running').percent,
    ).toBe(63);
  });

  it('en cola, terminada o fallida', () => {
    expect(stageProgress({}, 'pending')).toEqual({ label: 'En cola', percent: 0 });
    expect(stageProgress({ stage: 'close' }, 'completed')).toEqual({
      label: 'Terminada',
      percent: 100,
    });
    expect(stageProgress({}, 'failed').label).toBe('No se pudo completar');
  });
});

describe('textos', () => {
  it('dinero y precisión', () => {
    expect(formatUsd(0.0129)).toBe('0.0129 USD');
    expect(isCoarse('state')).toBe(true);
    expect(isCoarse('municipality')).toBe(false);
  });
});

describe('notas por concepto', () => {
  it('cuenta las relevantes por concepto y aparte las que no lo son', () => {
    const slices = conceptSlices(
      [
        article([[3, 'Extorsión', true]]),
        article([
          [3, 'Extorsión', true],
          [5, 'Secuestro', true],
        ]),
        article([[3, 'Extorsión', false]]),
      ],
      new Map([[3, '#AA0000']]),
    );

    expect(slices).toEqual([
      { conceptId: 3, name: 'Extorsión', color: '#AA0000', count: 2 },
      { conceptId: 5, name: 'Secuestro', color: NO_CONCEPT_COLOR, count: 1 },
      { conceptId: null, name: 'No relevantes', color: NO_CONCEPT_COLOR, count: 1 },
    ]);
  });
});
