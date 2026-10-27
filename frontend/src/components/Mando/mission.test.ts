/** Lógica del Centro de mando (diseño 3): frase, horario, misiones y bitácora. */
import { describe, expect, it } from 'vitest';

import type { Search } from '../../services/searches';
import type { SourceOption } from '../../services/sources';
import {
  clockLabel,
  conceptsLabel,
  countdownLabel,
  elapsedLabel,
  isMandoMode,
  missionLabel,
  missionLog,
  nextAutomaticRun,
  rangeConnector,
  rangeLabel,
  runLabel,
  recentMissions,
  shortConcept,
  sourcesLabel,
  spanDays,
  stageIndex,
} from './mission';

function search(overrides: Partial<Search> = {}): Search {
  return {
    search_id: 's1',
    status: 'completed',
    region_id: 14,
    region_code: '14',
    region_name: 'Jalisco',
    date_from: '2026-10-21',
    date_to: '2026-10-27',
    concepts: [{ id: 13, name: 'Fiscalía General de la República' }],
    progress: {},
    queries_planned: 4,
    credits_estimated: 0,
    credits_used: 0,
    llm_tokens_in: 0,
    llm_tokens_out: 0,
    llm_cost_usd: 0,
    results_count: 40,
    error_summary: null,
    created_at: '2026-10-27T18:00:00Z',
    started_at: '2026-10-27T18:00:00Z',
    finished_at: null,
    trigger: 'manual',
    scheduled_for: null,
    ...overrides,
  };
}

const SOURCES: SourceOption[] = [
  {
    id: 'google_news_rss',
    label: 'Google News RSS',
    paid: false,
    configured: true,
    default_on: true,
  },
  { id: 'indice_local', label: 'Índice local', paid: false, configured: true, default_on: true },
  { id: 'searchapi', label: 'SearchApi', paid: true, configured: true, default_on: false },
];

describe('isMandoMode', () => {
  it('es el diseño principal; ?clasico vuelve al de columna', () => {
    expect(isMandoMode('')).toBe(true);
    expect(isMandoMode('?mando')).toBe(true);
    expect(isMandoMode('?depurar')).toBe(true);
    expect(isMandoMode('?clasico')).toBe(false);
    expect(isMandoMode('?depurar&clasico')).toBe(false);
  });
});

describe('frase de la misión', () => {
  it('usa la sigla de los conceptos largos', () => {
    expect(shortConcept('Fiscalía General de la República')).toBe('FGR');
    expect(shortConcept('Extorsión')).toBe('Extorsión');
  });

  it('junta los conceptos como se dicen', () => {
    expect(conceptsLabel([])).toBe('elige un concepto');
    expect(conceptsLabel(['Extorsión'])).toBe('Extorsión');
    expect(conceptsLabel(['Extorsión', 'Robo'])).toBe('Extorsión y Robo');
    expect(conceptsLabel(['Extorsión', 'Robo', 'Fraude'])).toBe('Extorsión y 2 más');
  });

  it('dice el rango de fechas', () => {
    expect(rangeLabel({ kind: 'today' })).toBe('hoy');
    expect(rangeLabel({ kind: '7' })).toBe('los últimos 7 días');
    expect(rangeLabel({ kind: '30' })).toBe('los últimos 30 días');
    expect(rangeLabel({ kind: 'custom', from: '2026-10-10', to: '2026-10-17' })).toBe(
      '10 – 17 oct 2026',
    );
    expect(rangeLabel({ kind: 'custom' })).toBe('fechas por elegir');
  });

  it('une el rango con la palabra que le toca', () => {
    expect(rangeConnector({ kind: 'today' })).toBe('');
    expect(rangeConnector({ kind: '7' })).toBe('durante');
    expect(rangeConnector({ kind: 'custom' })).toBe('en el periodo');
  });

  it('cuenta las fuentes y avisa si alguna es de pago', () => {
    expect(sourcesLabel(SOURCES, [])).toBe('ninguna fuente');
    expect(sourcesLabel(SOURCES, ['indice_local'])).toBe('1 fuente gratis');
    expect(sourcesLabel(SOURCES, ['google_news_rss', 'indice_local'])).toBe('2 fuentes gratis');
    expect(sourcesLabel(SOURCES, ['google_news_rss', 'searchapi'])).toBe('2 fuentes · 1 de pago');
  });
});

describe('corridas automáticas y relojes', () => {
  it('encuentra la siguiente corrida en la Ciudad de México (UTC−6)', () => {
    // 13:00 en CDMX: faltan 2 h para la de las 15:00.
    expect(nextAutomaticRun(new Date('2026-10-27T19:00:00Z'))).toEqual({ hour: 15, seconds: 7200 });
    // 23:30 en CDMX: la siguiente es la de las 07:00 del día siguiente (7 h 30 min).
    expect(nextAutomaticRun(new Date('2026-10-28T05:30:00Z'))).toEqual({ hour: 7, seconds: 27000 });
    // 06:59:30: faltan 30 s para la de las 07:00.
    expect(nextAutomaticRun(new Date('2026-10-27T12:59:30Z'))).toEqual({ hour: 7, seconds: 30 });
  });

  it('dice cuánto falta en corto', () => {
    expect(countdownLabel(6120)).toBe('1 h 42 min');
    expect(countdownLabel(600)).toBe('10 min');
    expect(countdownLabel(45)).toBe('menos de 1 min');
  });

  it('marca la hora de la Ciudad de México y el cronómetro', () => {
    expect(clockLabel(new Date('2026-10-27T19:42:05Z'))).toBe('13:42:05');
    expect(elapsedLabel('2026-10-27T19:00:00Z', new Date('2026-10-27T19:01:05Z'))).toBe('01:05');
    expect(elapsedLabel(null, new Date())).toBe('00:00');
  });
});

describe('misiones recientes', () => {
  it('arma la ficha de la corrida automática con su hora de la Ciudad de México', () => {
    expect(runLabel({ scheduled_for: '2026-10-27T13:00:00Z', results_count: 305 })).toBe(
      'Corrida 07:00 · 305 notas',
    );
    expect(runLabel({ scheduled_for: null, results_count: 3 })).toBe('Corrida · 3 notas');
  });

  it('cuenta los días de la búsqueda y arma la ficha', () => {
    expect(spanDays('2026-10-21', '2026-10-27')).toBe(7);
    expect(missionLabel(search())).toBe('FGR · Jalisco · 7 días');
    expect(missionLabel(search({ date_from: '2026-10-27' }))).toBe('FGR · Jalisco · 1 día');
  });

  it('deja fuera las automáticas, las fallidas, las vacías y las repetidas', () => {
    const history = [
      search({ search_id: 'auto', trigger: 'automatic' }),
      search({ search_id: 'nueva' }),
      search({ search_id: 'repetida' }),
      search({ search_id: 'fallo', status: 'failed', region_id: 9 }),
      search({ search_id: 'vacia', results_count: 0, region_id: 15 }),
      search({ search_id: 'corriendo', status: 'running', region_id: 16 }),
      search({ search_id: 'otra', region_id: 9, region_name: 'CDMX' }),
      search({ search_id: 'tercera', region_id: 19 }),
      search({ search_id: 'sobra', region_id: 20 }),
    ];
    expect(recentMissions(history).map((s) => s.search_id)).toEqual(['nueva', 'otra', 'tercera']);
  });
});

describe('avance del barrido', () => {
  it('ubica la etapa en curso', () => {
    expect(stageIndex(search({ status: 'pending' }))).toBe(0);
    expect(stageIndex(search({ status: 'running', progress: { stage: 'enrich' } }))).toBe(4);
    expect(stageIndex(search({ status: 'completed' }))).toBe(8);
  });

  it('escribe la bitácora con los números que ya se conocen', () => {
    expect(missionLog(search({ status: 'pending' }))).toEqual([
      'En cola: el barrido arranca en un momento',
    ]);
    expect(missionLog(search({ status: 'running', progress: { stage: 'query' } }))).toEqual([
      'Plan: 4 consultas',
      'Consultando fuentes…',
    ]);
    expect(
      missionLog(
        search({
          status: 'running',
          progress: { stage: 'enrich', articles: 30, reused: 10, enriched: 5 },
        }),
      ),
    ).toEqual([
      'Plan: 4 consultas',
      'Fuentes consultadas: 30 notas',
      'Leyendo el texto de las notas',
      'IA: 5 de 20 · 10 ya conocidas',
    ]);
    const done = missionLog(
      search({ progress: { articles: 30, in_region: 25, out_of_region: 3, unlocated: 2 } }),
    );
    expect(done.slice(-2)).toEqual([
      '25 dentro · 3 fuera · 2 sin ubicar',
      'Barrido completo: 40 notas',
    ]);
  });
});
