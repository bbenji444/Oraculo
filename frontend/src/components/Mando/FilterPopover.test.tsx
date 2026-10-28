// @vitest-environment jsdom
/** Ventana «Filtro» del expediente, al centro de la pantalla (28/10/2026). */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useTimelineStore } from '../../store/timeline';
import { FilterPopover } from './FilterPopover';
import { activeFilters } from './mission';

const ORGANIZADA = { id: 2, name: 'Delincuencia organizada', color: '#9B8CFF', symbol: null };
const HUACHICOL = { id: 7, name: 'Huachicol', color: '#A3E635', symbol: null };

function note(id: number, at: string, category: Article['category']): Article {
  return {
    article_id: id,
    title: `Nota ${String(id)}`,
    source_name: null,
    source_domain: null,
    url: `https://medio.mx/${String(id)}`,
    published_at: at,
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts: [],
    primary_location: null,
    in_region: null,
    providers: [],
    category,
  };
}

// Corrida de las 07:00: notas de las 23:00, 01:00 y 06:00 (CDMX, UTC−6).
const NOTES = [
  note(1, '2026-10-28T05:10:00Z', HUACHICOL),
  note(2, '2026-10-28T07:20:00Z', HUACHICOL),
  note(3, '2026-10-28T12:05:00Z', ORGANIZADA),
  note(4, '2026-10-28T12:40:00Z', HUACHICOL),
];

beforeEach(() => {
  useTimelineStore.getState().clear();
  useExplorerStore.setState({ listFilter: 'all', showIrrelevant: false });
});
afterEach(cleanup);

describe('FilterPopover', () => {
  it('«Filtro» abre la ventana y dice cuántos filtros hay puestos', () => {
    render(<FilterPopover articles={NOTES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Filtro' }));
    const dialog = screen.getByRole('dialog', { name: 'Filtrar el expediente' });
    fireEvent.click(within(dialog).getByRole('button', { name: /Delincuencia organizada/ }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Fuera' }));
    expect(useTimelineStore.getState().categoryIds).toEqual([2]);
    expect(useExplorerStore.getState().listFilter).toBe('false');
    expect(screen.getByRole('button', { name: /^Filtro/ }).textContent).toBe('Filtro2');
    // El estado es una lista desplegable.
    expect(within(dialog).getByLabelText('Estado').textContent).toBe('Todos los estados');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Quitar filtros' }));
    expect(useTimelineStore.getState().categoryIds).toEqual([]);
    expect(useExplorerStore.getState().listFilter).toBe('all');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Listo' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('cuenta categorías, estado, ubicación y no relevantes', () => {
    expect(activeFilters([], null, 'all', false)).toBe(0);
    expect(activeFilters([2, 7], '08', 'none', true)).toBe(5);
  });
});
