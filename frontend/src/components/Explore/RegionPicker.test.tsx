// @vitest-environment jsdom
/** Selector de región: «Todo México» queda elegido de verdad (Benji, 09/11/2026). */
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useExplorerStore } from '../../store/explorer';
import { RegionPicker } from './RegionPicker';

const MEXICO_ID = 258;

vi.mock('../../hooks/useRegions', () => ({
  useRegionDetail: () => ({ data: undefined }),
  useRegionsByLevel: () => ({
    data: [
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
});
