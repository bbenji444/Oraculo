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
    fireEvent.click(within(dialog).getByRole('button', { name: 'Fuera de zona' }));
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

  it('cuenta categorías, plataformas, estado, ubicación y no relevantes', () => {
    expect(activeFilters([], null, 'all', false, [])).toBe(0);
    expect(activeFilters([2, 7], '08', 'none', true, [])).toBe(5);
    // Cada plataforma elegida cuenta, como cada categoría (ADR-0117).
    expect(activeFilters([], null, 'all', false, ['facebook'])).toBe(1);
    expect(activeFilters([2], '08', 'all', false, ['facebook', 'x'])).toBe(4);
  });

  it('la sección «Plataforma» elige varias y «Quitar filtros» las limpia', () => {
    const social = [
      ...NOTES,
      { ...note(5, '2026-10-28T12:50:00Z', HUACHICOL), platform: 'facebook' as const },
      { ...note(6, '2026-10-28T12:55:00Z', HUACHICOL), platform: 'x' as const },
    ];
    render(<FilterPopover articles={social} />);
    fireEvent.click(screen.getByRole('button', { name: 'Filtro' }));
    const dialog = screen.getByRole('dialog', { name: 'Filtrar el expediente' });
    const section = within(dialog).getByRole('region', { name: 'Plataforma' });
    // Va antes que las categorías.
    const order = [...dialog.querySelectorAll('section')].map((s) => s.getAttribute('aria-label'));
    expect(order.indexOf('Plataforma')).toBeLessThan(order.indexOf('Categorías'));
    const group = within(section).getByRole('group', { name: 'Plataformas a mostrar' });
    expect(within(group).getByRole('button', { name: /^Noticias/ }).textContent).toBe('Noticias4');

    fireEvent.click(within(group).getByRole('button', { name: /^Facebook/ }));
    fireEvent.click(within(group).getByRole('button', { name: /^X/ }));

    expect(useTimelineStore.getState().platforms).toEqual(['facebook', 'x']);
    expect(screen.getByRole('button', { name: /^Filtro/ }).textContent).toBe('Filtro2');
    // Volver a tocar una la apaga y deja la otra.
    fireEvent.click(within(group).getByRole('button', { name: /^X/ }));
    expect(useTimelineStore.getState().platforms).toEqual(['facebook']);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Quitar filtros' }));
    expect(useTimelineStore.getState().platforms).toEqual([]);
  });

  it('«Plataforma» cuenta con las mismas notas que las pestañas del expediente', () => {
    const social = [
      ...NOTES,
      { ...note(5, '2026-10-28T12:50:00Z', HUACHICOL), platform: 'facebook' as const },
      { ...note(6, '2026-10-28T12:55:00Z', ORGANIZADA), platform: 'facebook' as const },
      { ...note(7, '2026-10-28T12:58:00Z', ORGANIZADA), platform: 'x' as const },
    ];
    // Con «Delincuencia organizada» elegida, las pestañas cuentan solo esas.
    const faceted = social.filter((a) => a.category?.id === ORGANIZADA.id);
    render(<FilterPopover articles={social} platformArticles={faceted} />);
    fireEvent.click(screen.getByRole('button', { name: 'Filtro' }));
    const group = screen.getByRole('group', { name: 'Plataformas a mostrar' });
    expect(
      within(group)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Todas', 'Noticias1', 'Facebook1', 'X1']);
  });

  it('el interruptor de no relevantes no dice que las demás no tratan del tema', () => {
    render(<FilterPopover articles={NOTES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Filtro' }));
    const dialog = screen.getByRole('dialog', { name: 'Filtrar el expediente' });
    expect(dialog.textContent).not.toMatch(/no tienen nada que ver|no tratan del tema/);
    expect(dialog.textContent).toContain('que descartó la IA');
  });

  it('sin más de una plataforma no hay sección «Plataforma»', () => {
    render(<FilterPopover articles={NOTES} />);
    fireEvent.click(screen.getByRole('button', { name: 'Filtro' }));
    const dialog = screen.getByRole('dialog', { name: 'Filtrar el expediente' });
    expect(within(dialog).queryByRole('region', { name: 'Plataforma' })).toBeNull();
  });
});
