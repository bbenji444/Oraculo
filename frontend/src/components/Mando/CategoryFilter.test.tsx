// @vitest-environment jsdom
/** Botones de color por categoría del expediente (28/10/2026). */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import { useTimelineStore } from '../../store/timeline';
import { CategoryFilter } from './CategoryFilter';

const ORGANIZADA = { id: 2, name: 'Delincuencia organizada', color: '#9B8CFF', symbol: null };
const HUACHICOL = {
  id: 7,
  name: 'Huachicol y delitos contra hidrocarburos',
  color: '#A3E635',
  symbol: null,
};

function note(id: number, category: Article['category']): Article {
  return {
    article_id: id,
    title: `Nota ${String(id)}`,
    source_name: null,
    source_domain: null,
    url: `https://medio.mx/${String(id)}`,
    published_at: null,
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

const NOTES = [note(1, HUACHICOL), note(2, HUACHICOL), note(3, ORGANIZADA)];

beforeEach(() => {
  useTimelineStore.getState().clear();
});
afterEach(cleanup);

describe('CategoryFilter', () => {
  it('un botón por categoría, de la que más sale a la que menos', () => {
    render(<CategoryFilter articles={NOTES} />);
    const names = screen.getAllByRole('button').map((b) => b.textContent);
    expect(names).toEqual([
      'Todas',
      'Huachicol y delitos contra hidrocarburos2',
      'Delincuencia organizada1',
    ]);
  });

  it('se prenden una o varias, y «Todas» las apaga', () => {
    render(<CategoryFilter articles={NOTES} />);
    fireEvent.click(screen.getByRole('button', { name: /Delincuencia organizada/ }));
    expect(useTimelineStore.getState().categoryIds).toEqual([2]);
    fireEvent.click(screen.getByRole('button', { name: /Huachicol/ }));
    expect(useTimelineStore.getState().categoryIds).toEqual([2, 7]);
    fireEvent.click(screen.getByRole('button', { name: /Delincuencia organizada/ }));
    expect(useTimelineStore.getState().categoryIds).toEqual([7]);
    fireEvent.click(screen.getByRole('button', { name: 'Todas' }));
    expect(useTimelineStore.getState().categoryIds).toEqual([]);
  });

  it('dice cuál está prendida', () => {
    render(<CategoryFilter articles={NOTES} />);
    fireEvent.click(screen.getByRole('button', { name: /Huachicol/ }));
    expect(screen.getByRole('button', { name: /Huachicol/ }).getAttribute('aria-pressed')).toBe(
      'true',
    );
    expect(screen.getByRole('button', { name: 'Todas' }).getAttribute('aria-pressed')).toBe(
      'false',
    );
  });
});
