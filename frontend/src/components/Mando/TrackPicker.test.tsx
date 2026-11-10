// @vitest-environment jsdom
/** Ventana «¿Qué rastrear?»: con quién y qué delitos, en una sola lista (09/11/2026). */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Category } from '../../services/categories';
import type { Concept } from '../../services/concepts';
import { useExplorerStore } from '../../store/explorer';
import { TrackPicker } from './TrackPicker';
import { trackSummary } from './trackSummary';

function concept(id: number, name: string, categoryId: number | null, color: string): Concept {
  return {
    id,
    name,
    description: '',
    keywords: [name.toLowerCase()],
    exclude_terms: [],
    color,
    is_active: true,
    category_id: categoryId,
    created_by: 'semilla',
    created_at: '2026-11-02T18:00:00Z',
    updated_at: '2026-11-02T18:00:00Z',
  };
}

function category(id: number, name: string, topic: number | null, isOther = false): Category {
  return {
    id,
    name,
    description: '',
    is_other: isOther,
    color: '#FF4D6D',
    symbol: null,
    is_active: true,
    topic_concept_id: topic,
  };
}

const FGR = concept(13, 'Fiscalía General de la República', null, '#00D2FF');
const HOMICIDIO = concept(21, 'Homicidio', 5, '#FF4D6D');
const SECUESTRO = concept(22, 'Secuestro', 3, '#F472B6');
const CATEGORIES = [
  category(3, 'Secuestro', 22),
  category(5, 'Homicidio', 21),
  category(14, 'Otros', null, true),
];

vi.mock('../../hooks/useConcepts', () => ({
  useConcepts: () => ({ data: [FGR, HOMICIDIO, SECUESTRO] }),
}));
vi.mock('../../hooks/useCategories', () => ({
  useCategories: () => ({ data: CATEGORIES }),
}));

const initial = useExplorerStore.getState();

beforeEach(() => {
  useExplorerStore.setState(initial, true);
});
afterEach(cleanup);

function groups() {
  return {
    anchors: screen.getByRole('group', { name: 'Relacionados con' }),
    crimes: screen.getByRole('group', { name: 'Delitos' }),
  };
}

function summary() {
  return screen.getByRole('status').textContent;
}

describe('TrackPicker', () => {
  it('cada delito sale una sola vez, sin «Otros»', () => {
    render(<TrackPicker onClose={vi.fn()} />);
    const { anchors, crimes } = groups();

    expect(
      within(anchors)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual([FGR.name, 'Con nadie en particular']);
    expect(
      within(crimes)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Todos', 'Secuestro', 'Homicidio']);
    expect(screen.getAllByRole('button', { name: 'Homicidio' })).toHaveLength(1);
  });

  it('FGR con delitos trae las notas que tienen las dos cosas', () => {
    render(<TrackPicker onClose={vi.fn()} />);
    const { anchors, crimes } = groups();

    fireEvent.click(within(anchors).getByRole('button', { name: FGR.name }));
    fireEvent.click(within(crimes).getByRole('button', { name: 'Homicidio' }));
    fireEvent.click(within(crimes).getByRole('button', { name: 'Secuestro' }));

    expect(useExplorerStore.getState().conceptIds).toEqual([FGR.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([5, 3]);
    expect(summary()).toBe(`Notas de ${FGR.name} que además hablan de Secuestro o Homicidio.`);

    fireEvent.click(within(crimes).getByRole('button', { name: 'Todos' }));
    expect(useExplorerStore.getState().subdivisionIds).toEqual([]);
    expect(summary()).toBe(`Todo lo de ${FGR.name}, de cualquier delito.`);
  });

  it('un delito sin nadie elegido se busca con la FGR', () => {
    render(<TrackPicker onClose={vi.fn()} />);

    fireEvent.click(within(groups().crimes).getByRole('button', { name: 'Homicidio' }));

    expect(useExplorerStore.getState().conceptIds).toEqual([FGR.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([5]);
  });

  it('«Con nadie en particular» busca cada delito por su cuenta', () => {
    render(<TrackPicker onClose={vi.fn()} />);
    const { anchors, crimes } = groups();

    fireEvent.click(within(anchors).getByRole('button', { name: 'Con nadie en particular' }));
    expect(summary()).toBe('Elige al menos un delito.');
    expect(within(crimes).getByRole('button', { name: 'Todos' })).toHaveProperty('disabled', true);

    fireEvent.click(within(crimes).getByRole('button', { name: 'Homicidio' }));
    fireEvent.click(within(crimes).getByRole('button', { name: 'Secuestro' }));

    expect(useExplorerStore.getState().conceptIds).toEqual([HOMICIDIO.id, SECUESTRO.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([]);
    expect(summary()).toBe(
      'Todas las notas de Secuestro o Homicidio, aparezca o no alguien en particular.',
    );
  });

  it('cambiar de quién conserva los delitos elegidos', () => {
    // Benji, 03/11/2026: la FGR y los delitos en general no se mezclan.
    useExplorerStore.setState({ conceptIds: [FGR.id], subdivisionIds: [5] });
    render(<TrackPicker onClose={vi.fn()} />);
    const { anchors } = groups();

    fireEvent.click(within(anchors).getByRole('button', { name: 'Con nadie en particular' }));
    expect(useExplorerStore.getState().conceptIds).toEqual([HOMICIDIO.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([]);

    fireEvent.click(within(anchors).getByRole('button', { name: FGR.name }));
    expect(useExplorerStore.getState().conceptIds).toEqual([FGR.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([5]);
  });

  it('quitar a la FGR quita sus delitos', () => {
    useExplorerStore.setState({ conceptIds: [FGR.id], subdivisionIds: [5] });
    render(<TrackPicker onClose={vi.fn()} />);

    fireEvent.click(within(groups().anchors).getByRole('button', { name: FGR.name }));

    expect(useExplorerStore.getState().conceptIds).toEqual([]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([]);
  });

  it('una búsqueda reabierta con FGR y un tema suelto se corrige al elegir delito', () => {
    useExplorerStore.setState({ conceptIds: [FGR.id, HOMICIDIO.id], subdivisionIds: [] });
    render(<TrackPicker onClose={vi.fn()} />);

    fireEvent.click(within(groups().crimes).getByRole('button', { name: 'Secuestro' }));

    expect(useExplorerStore.getState().conceptIds).toEqual([FGR.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([3]);
  });

  it('se cierra con Esc y con «Listo»', () => {
    const onClose = vi.fn();
    render(<TrackPicker onClose={onClose} />);

    fireEvent.keyDown(window, { key: 'Escape' });
    fireEvent.click(screen.getByRole('button', { name: 'Listo' }));

    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe('trackSummary', () => {
  it('dice en palabras qué trae la búsqueda', () => {
    expect(trackSummary([], [], false)).toBe('Elige con quién o un delito.');
    expect(trackSummary(['FGR', 'PDI'], [], false)).toBe(
      'Todo lo de FGR o PDI, de cualquier delito.',
    );
    expect(trackSummary(['FGR'], ['Homicidio', 'Secuestro', 'Extorsión'], false)).toBe(
      'Notas de FGR que además hablan de Homicidio, Secuestro o Extorsión.',
    );
  });
});
