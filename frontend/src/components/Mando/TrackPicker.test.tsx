// @vitest-environment jsdom
/** Ventana «¿Qué rastrear?»: la FGR con sus subdivisiones y los temas generales (02/11/2026). */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Category } from '../../services/categories';
import type { Concept } from '../../services/concepts';
import { useExplorerStore } from '../../store/explorer';
import { TrackPicker } from './TrackPicker';

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
    subdivisions: screen.getByRole('group', { name: 'Subdivisiones de la FGR' }),
    topics: screen.getByRole('group', { name: 'Temas generales' }),
  };
}

describe('TrackPicker', () => {
  it('muestra las subdivisiones buscables y sus temas, sin «Otros»', () => {
    render(<TrackPicker onClose={vi.fn()} />);
    const { subdivisions, topics } = groups();

    expect(
      within(subdivisions)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Todas', 'Secuestro', 'Homicidio']);
    expect(
      within(topics)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Secuestro', 'Homicidio']);
  });

  it('una subdivisión prende la FGR y se busca con las dos', () => {
    render(<TrackPicker onClose={vi.fn()} />);
    const { subdivisions } = groups();

    fireEvent.click(within(subdivisions).getByRole('button', { name: 'Homicidio' }));
    fireEvent.click(within(subdivisions).getByRole('button', { name: 'Secuestro' }));

    expect(useExplorerStore.getState().conceptIds).toEqual([FGR.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([5, 3]);

    fireEvent.click(within(subdivisions).getByRole('button', { name: 'Todas' }));
    expect(useExplorerStore.getState().subdivisionIds).toEqual([]);
    expect(useExplorerStore.getState().conceptIds).toEqual([FGR.id]);
  });

  it('apagar la FGR quita sus subdivisiones', () => {
    useExplorerStore.setState({ conceptIds: [FGR.id], subdivisionIds: [5] });
    render(<TrackPicker onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: FGR.name }));

    expect(useExplorerStore.getState().conceptIds).toEqual([]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([]);
  });

  it('un tema general se elige por su cuenta, sin la FGR', () => {
    render(<TrackPicker onClose={vi.fn()} />);

    fireEvent.click(within(groups().topics).getByRole('button', { name: 'Homicidio' }));

    expect(useExplorerStore.getState().conceptIds).toEqual([HOMICIDIO.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([]);
  });

  it('la FGR y los temas generales no se mezclan', () => {
    // Benji, 03/11/2026: con la FGR elegida no quiere homicidios en general.
    // FGR + el tema «Homicidio» sumaría toda la FGR y todos los homicidios.
    useExplorerStore.setState({ conceptIds: [FGR.id], subdivisionIds: [5] });
    render(<TrackPicker onClose={vi.fn()} />);
    const { subdivisions, topics } = groups();

    fireEvent.click(within(topics).getByRole('button', { name: 'Homicidio' }));
    expect(useExplorerStore.getState().conceptIds).toEqual([HOMICIDIO.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([]);

    // Varios temas sí van juntos.
    fireEvent.click(within(topics).getByRole('button', { name: 'Secuestro' }));
    expect(useExplorerStore.getState().conceptIds).toEqual([HOMICIDIO.id, SECUESTRO.id]);

    // Y volver a la FGR apaga los temas.
    fireEvent.click(within(subdivisions).getByRole('button', { name: 'Homicidio' }));
    expect(useExplorerStore.getState().conceptIds).toEqual([FGR.id]);
    expect(useExplorerStore.getState().subdivisionIds).toEqual([5]);

    fireEvent.click(within(topics).getByRole('button', { name: 'Secuestro' }));
    fireEvent.click(screen.getByRole('button', { name: FGR.name }));
    expect(useExplorerStore.getState().conceptIds).toEqual([FGR.id]);
  });

  it('una búsqueda reabierta con FGR y un tema suelto se corrige al elegir subdivisión', () => {
    useExplorerStore.setState({ conceptIds: [FGR.id, HOMICIDIO.id], subdivisionIds: [] });
    render(<TrackPicker onClose={vi.fn()} />);

    fireEvent.click(within(groups().subdivisions).getByRole('button', { name: 'Secuestro' }));

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
