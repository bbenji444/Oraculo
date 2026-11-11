// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useExplorerStore } from '../../store/explorer';
import { IDLE_SPIN_MS, useIdleSpin } from './useIdleSpin';

describe('giro tras 5 minutos sin tocar nada (11/11/2026)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useExplorerStore.setState({ motion: 'slow', spinning: false, searchId: 'abc', regionId: 9 });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('con una búsqueda abierta gira a los 5 minutos y se detiene al volver', () => {
    const { unmount } = renderHook(() => {
      useIdleSpin(true);
    });

    vi.advanceTimersByTime(IDLE_SPIN_MS - 1000);
    expect(useExplorerStore.getState().spinning).toBe(false);
    vi.advanceTimersByTime(1000);
    expect(useExplorerStore.getState().spinning).toBe(true);

    window.dispatchEvent(new Event('pointerdown'));
    expect(useExplorerStore.getState().spinning).toBe(false);
    unmount();
  });

  it('cualquier movimiento reinicia la cuenta', () => {
    const { unmount } = renderHook(() => {
      useIdleSpin(true);
    });

    vi.advanceTimersByTime(IDLE_SPIN_MS - 1000);
    window.dispatchEvent(new Event('keydown'));
    vi.advanceTimersByTime(IDLE_SPIN_MS - 1000);

    expect(useExplorerStore.getState().spinning).toBe(false);
    unmount();
  });

  it('fuera de Explorar o sin animación no hace nada', () => {
    const hidden = renderHook(() => {
      useIdleSpin(false);
    });
    vi.advanceTimersByTime(IDLE_SPIN_MS);
    expect(useExplorerStore.getState().spinning).toBe(false);
    hidden.unmount();

    useExplorerStore.setState({ motion: 'off' });
    const off = renderHook(() => {
      useIdleSpin(true);
    });
    vi.advanceTimersByTime(IDLE_SPIN_MS);
    expect(useExplorerStore.getState().spinning).toBe(false);
    off.unmount();
  });
});
