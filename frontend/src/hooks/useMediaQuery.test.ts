// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useMediaQuery } from './useMediaQuery';

describe('useMediaQuery', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sin matchMedia responde el valor de respaldo', () => {
    vi.stubGlobal('matchMedia', undefined);
    expect(renderHook(() => useMediaQuery('(min-width: 768px)', true)).result.current).toBe(true);
    expect(renderHook(() => useMediaQuery('(min-width: 768px)')).result.current).toBe(false);
  });

  it('con matchMedia responde lo que dice la ventana', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query === '(min-width: 768px)',
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    expect(renderHook(() => useMediaQuery('(min-width: 768px)')).result.current).toBe(true);
    expect(renderHook(() => useMediaQuery('(min-width: 2000px)')).result.current).toBe(false);
  });
});
