import { describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import {
  authorityNote,
  automaticRunLabel,
  eventDateNote,
  finishNotice,
  formatDay,
  formatMexicoCity,
  formatRange,
  formatUsd,
  isCoarse,
  newsCount,
  providersLabel,
  stageProgress,
  visibleArticles,
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

describe('notas visibles (lista y globo)', () => {
  const kept = article([[3, 'Extorsión', true]]);
  const discarded = article([[3, 'Extorsión', false]]);

  it('por defecto solo las relevantes para algún concepto', () => {
    expect(visibleArticles([kept, discarded], false)).toEqual([kept]);
  });

  it('con "No relevantes" se ven todas', () => {
    expect(visibleArticles([kept, discarded], true)).toEqual([kept, discarded]);
  });
});

describe('periodo corto', () => {
  it('mismo mes, otro mes y otro año', () => {
    expect(formatRange('2026-10-10', '2026-10-17')).toBe('10 – 17 oct 2026');
    expect(formatRange('2026-09-28', '2026-10-05')).toBe('28 sep – 5 oct 2026');
    expect(formatRange('2025-12-28', '2026-01-04')).toBe('28 dic 2025 – 4 ene 2026');
  });
});

describe('aviso al terminar', () => {
  it('dice cuántas notas hay y si hubo avisos o falla', () => {
    expect(finishNotice({ status: 'completed', results_count: 18 })).toEqual({
      tone: 'ok',
      text: 'Búsqueda lista: 18 notas',
    });
    expect(finishNotice({ status: 'completed', results_count: 1 }).text).toBe(
      'Búsqueda lista: 1 nota',
    );
    expect(finishNotice({ status: 'partial', results_count: 4 }).tone).toBe('warn');
    expect(finishNotice({ status: 'failed', results_count: 0 })).toEqual({
      tone: 'error',
      text: 'La búsqueda falló',
    });
  });
});

describe('fecha del hecho', () => {
  it('se avisa cuando la nota es un avance de un hecho de otro momento', () => {
    expect(eventDateNote('2025-09-29', '2026-10-16T14:00:00Z')).toBe(
      'Se refiere a hechos del 29 sep 2025',
    );
    expect(eventDateNote('2026-10-30', '2026-10-15T14:00:00Z')).toBe(
      'Se refiere a hechos del 30 oct 2026',
    );
  });

  it('no se repite si es del mismo día o casi', () => {
    expect(eventDateNote('2026-10-15', '2026-10-16T05:00:00Z')).toBeNull();
    expect(eventDateNote(null, '2026-10-16T05:00:00Z')).toBeNull();
    expect(eventDateNote('2026-10-15', null)).toBeNull();
  });
});

describe('cuenta de noticias de la lista', () => {
  it('dice cuántas se ocultaron por no relevantes', () => {
    // Prueba operativa del 20/10/2026: arriba "43 notas", en la lista "Noticias (24)".
    expect(newsCount(24, 43)).toEqual({
      label: 'Noticias (24 de 43)',
      hint: '19 no relevantes ocultas: actívalas con «No relevantes». Las descargas incluyen solo las relevantes.',
    });
  });

  it('sin ocultas, solo el total', () => {
    expect(newsCount(43, 43)).toEqual({
      label: 'Noticias (43)',
      hint: 'Las descargas incluyen solo las notas relevantes.',
    });
    expect(newsCount(1, 2).hint).toMatch(/^1 no relevante oculta:/);
  });
});

describe('nombre de las fuentes (F12.2)', () => {
  it('une los nombres y deja tal cual un id desconocido', () => {
    expect(providersLabel(['google_news_rss', 'indice_local'])).toBe(
      'Google News RSS · Índice local',
    );
    expect(providersLabel(['searchapi', 'browserwork_bing'])).toBe('SearchApi · Bing');
    expect(providersLabel(['otra_fuente'])).toBe('otra_fuente');
    expect(providersLabel([])).toBe('');
  });
});

describe('authorityNote', () => {
  it('dice quién actúa (F12.5)', () => {
    expect(authorityNote('estatal')).toBe('Quién actúa: Fiscalía estatal');
    expect(authorityNote('fgr')).toBe('Quién actúa: FGR federal');
    expect(authorityNote('fgr_mencion')).toBe('Quién actúa: FGR solo mencionada');
  });

  it('sin dato o sin clasificar no muestra el renglón', () => {
    expect(authorityNote('sin_dato')).toBeNull();
    expect(authorityNote(null)).toBeNull();
    expect(authorityNote(undefined)).toBeNull();
  });
});

describe('automaticRunLabel', () => {
  it('dice de qué corrida del monitor es, en hora de la CDMX (F12.8)', () => {
    // 05:00 UTC = 23:00 del día anterior en la CDMX.
    expect(automaticRunLabel({ trigger: 'automatic', scheduled_for: '2026-10-26T05:00:00Z' })).toBe(
      'Monitor automático · corrida de las 23:00 del 25 oct',
    );
    expect(automaticRunLabel({ trigger: 'automatic', scheduled_for: '2026-10-26T13:00:00Z' })).toBe(
      'Monitor automático · corrida de las 07:00 del 26 oct',
    );
  });

  it('una búsqueda de una persona no lleva rótulo', () => {
    expect(automaticRunLabel({ trigger: 'manual', scheduled_for: null })).toBeNull();
    expect(automaticRunLabel({})).toBeNull();
  });
});
