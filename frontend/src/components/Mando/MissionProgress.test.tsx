// @vitest-environment jsdom
/** Avance del barrido y radar del Centro de mando (diseño 3). */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { Search } from '../../services/searches';
import { useQuickSearchStore } from '../../store/quickSearch';
import { MissionProgress } from './MissionProgress';
import { ScanOverlay } from './ScanOverlay';

afterEach(cleanup);

function search(overrides: Partial<Search> = {}): Search {
  return {
    search_id: 's1',
    status: 'running',
    region_id: 14,
    region_code: '14',
    region_name: 'Jalisco',
    date_from: '2026-10-27',
    date_to: '2026-10-27',
    concepts: [{ id: 13, name: 'Fiscalía General de la República' }],
    progress: { stage: 'enrich', articles: 30, reused: 10, enriched: 5 },
    queries_planned: 3,
    credits_estimated: 0,
    credits_used: 0,
    llm_tokens_in: 0,
    llm_tokens_out: 0,
    llm_cost_usd: 0,
    results_count: 0,
    error_summary: null,
    created_at: '2026-10-27T19:00:00Z',
    started_at: '2026-10-27T19:00:00Z',
    finished_at: null,
    trigger: 'manual',
    scheduled_for: null,
    ...overrides,
  };
}

describe('MissionProgress', () => {
  it('enciende las etapas hechas y marca la que va en curso', () => {
    render(<MissionProgress search={search()} />);
    const nodes = within(screen.getByRole('list', { name: 'Etapas del barrido' })).getAllByRole(
      'listitem',
    );
    expect(nodes).toHaveLength(8);
    expect(nodes.map((node) => node.dataset.state)).toEqual([
      'done',
      'done',
      'done',
      'done',
      'active',
      'todo',
      'todo',
      'todo',
    ]);
    expect(nodes[4]?.getAttribute('aria-current')).toBe('step');
    expect(screen.getByText('Etapa 5 de 8')).toBeTruthy();
  });

  it('escribe en la bitácora lo último que se sabe', () => {
    render(<MissionProgress search={search()} />);
    const log = screen.getByRole('list', { name: 'Bitácora del barrido' });
    expect(within(log).getByText('IA leyendo: 5 de 20 nuevas · 10 ya leídas antes')).toBeTruthy();
  });

  it('marca en rojo la etapa donde se cayó el barrido', () => {
    render(
      <MissionProgress
        search={search({ status: 'failed', error_summary: 'Se cayó el proveedor' })}
      />,
    );
    expect(screen.getByText('Se cayó el proveedor')).toBeTruthy();
    const nodes = within(screen.getByRole('list', { name: 'Etapas del barrido' })).getAllByRole(
      'listitem',
    );
    expect(nodes.every((node) => node.dataset.state === 'done')).toBe(true);
  });

  it('dice si Google web no pudo buscar: el aviso del worker y el del lanzamiento (ADR-0115)', () => {
    const LAUNCH = 'Sin créditos de Google web: se buscó en noticias';
    const WORKER = 'Google web no respondió: se buscó con las demás fuentes';
    useQuickSearchStore.getState().remember({
      searchId: 's1',
      conceptId: 41,
      conceptName: 'Hacker Eternal',
      text: 'hacker eternal',
      notice: LAUNCH,
    });
    const { rerender } = render(<MissionProgress search={search()} />);
    const notices = screen.getByRole('list', { name: 'Avisos de la búsqueda' });
    expect(within(notices).getByText(LAUNCH)).toBeTruthy();

    rerender(
      <MissionProgress search={search({ progress: { stage: 'enrich', notice: WORKER } })} />,
    );
    expect(
      within(screen.getByRole('list', { name: 'Avisos de la búsqueda' }))
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual([LAUNCH, WORKER]);

    // Otra búsqueda sin aviso: no queda el de la anterior.
    rerender(<MissionProgress search={search({ search_id: 's2' })} />);
    expect(screen.queryByRole('list', { name: 'Avisos de la búsqueda' })).toBeNull();
    useQuickSearchStore.setState({ last: null });
  });
});

describe('ScanOverlay', () => {
  it('barre el globo mientras corre y se quita al terminar', () => {
    const { rerender } = render(
      <ScanOverlay search={search()} notice={null} right={0} bottom={120} />,
    );
    expect(screen.getByText('Barrido en curso · Jalisco')).toBeTruthy();
    rerender(
      <ScanOverlay
        search={search({ status: 'completed', results_count: 56 })}
        notice={{ tone: 'ok', text: 'Búsqueda lista: 56 notas' }}
        right={432}
        bottom={104}
      />,
    );
    expect(screen.queryByText('Barrido en curso · Jalisco')).toBeNull();
    const status = screen.getByRole('status');
    expect(status.textContent).toContain('BARRIDO COMPLETO');
    expect(status.textContent).toContain('Búsqueda lista: 56 notas');
  });
});
