/** Última corrida del monitor FGR para el acceso directo de Explorar (F12.8). */
import { describe, expect, it } from 'vitest';

import type { Search } from '../../services/searches';
import { latestRun } from './format';

function search(id: string, trigger: 'manual' | 'automatic', status: Search['status']): Search {
  return {
    search_id: id,
    status,
    region_id: 258,
    region_code: 'MEX',
    region_name: 'México',
    date_from: '2026-10-25',
    date_to: '2026-10-26',
    concepts: [{ id: 13, name: 'Fiscalia General de la Republica' }],
    progress: {},
    queries_planned: 2,
    credits_estimated: 0,
    credits_used: 0,
    llm_tokens_in: 0,
    llm_tokens_out: 0,
    llm_cost_usd: 0,
    results_count: 162,
    error_summary: null,
    created_at: '2026-10-26T09:45:00Z',
    started_at: null,
    finished_at: null,
    trigger,
    scheduled_for: trigger === 'automatic' ? '2026-10-26T05:00:00Z' : null,
  };
}

describe('latestRun', () => {
  it('toma la corrida automática terminada más reciente (el historial viene de la más nueva)', () => {
    const history = [
      search('manual', 'manual', 'completed'),
      search('corriendo', 'automatic', 'running'),
      search('ultima', 'automatic', 'completed'),
      search('vieja', 'automatic', 'completed'),
    ];

    expect(latestRun(history)?.search_id).toBe('ultima');
  });

  it('sin corridas automáticas no hay acceso directo', () => {
    expect(latestRun([search('manual', 'manual', 'completed')])).toBeUndefined();
  });
});
