// @vitest-environment jsdom
/**
 * Selector de región: «Todo México» queda elegido de verdad (Benji,
 * 09/11/2026) y «Todo el mundo» busca sin país (ADR-0112).
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useExplorerStore } from '../../store/explorer';
import { RegionPicker } from './RegionPicker';

const MEXICO_ID = 258;
const WORLD_ID = 999;
const WORLD = {
  id: WORLD_ID,
  level: 'world',
  name: 'Mundo',
  display_name: 'Mundo',
  parent_id: null,
  ancestors: [],
};
// La región que devuelve el detalle; cada prueba la cambia si la necesita.
let detail: typeof WORLD | undefined;

vi.mock('../../hooks/useRegions', () => ({
  useRegionDetail: () => ({ data: detail }),
  useRegionsByLevel: (level: string) => ({
    data:
      level === 'world'
        ? [WORLD]
        : [
            { id: 259, name: 'Aguascalientes', parent_id: MEXICO_ID },
            { id: 260, name: 'Baja California', parent_id: MEXICO_ID },
          ],
  }),
  useChildRegions: () => ({ data: undefined }),
}));
vi.mock('../GeoExplorer/SearchBox', () => ({ SearchBox: () => null }));

const initial = useExplorerStore.getState();

beforeEach(() => {
  useExplorerStore.setState(initial, true);
  detail = undefined;
});
afterEach(cleanup);

describe('RegionPicker', () => {
  it('sin región elegida, deja elegido Todo México para poder barrer', async () => {
    expect(useExplorerStore.getState().regionId).toBeNull();

    render(<RegionPicker />);

    await waitFor(() => {
      expect(useExplorerStore.getState().regionId).toBe(MEXICO_ID);
    });
  });

  it('no cambia una región que ya estaba elegida', () => {
    useExplorerStore.getState().selectRegion(260);

    render(<RegionPicker />);

    expect(useExplorerStore.getState().regionId).toBe(260);
  });

  it('«Todo el mundo» elige la región Mundo', () => {
    useExplorerStore.getState().selectRegion(260);
    render(<RegionPicker />);

    fireEvent.click(screen.getByRole('button', { name: 'Todo el mundo' }));

    expect(useExplorerStore.getState().regionId).toBe(WORLD_ID);
  });

  it('en el mundo no hay estados que elegir y «México» regresa a México', () => {
    useExplorerStore.getState().selectRegion(WORLD_ID);
    detail = WORLD;
    render(<RegionPicker />);

    expect(screen.getByRole('button', { name: 'Todo el mundo' }).getAttribute('aria-pressed')).toBe(
      'true',
    );
    screen.getByText(/Noticias en español de cualquier país/);
    expect(screen.queryByRole('combobox', { name: 'Estado' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'México' }));

    expect(useExplorerStore.getState().regionId).toBe(MEXICO_ID);
  });
});
