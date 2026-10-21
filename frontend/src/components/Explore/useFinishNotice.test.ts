// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Search } from '../../services/searches';
import search from '../../test/fixtures/explorar/search.json';
import { NOTICE_MS, useFinishNotice } from './useFinishNotice';

const finished = search as Search;
const running: Search = { ...finished, status: 'running', results_count: 0 };

function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
}

beforeEach(() => {
  vi.useFakeTimers();
  document.title = 'Monitor de Noticias';
  setHidden(false);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('aviso al terminar la búsqueda', () => {
  it('avisa al terminar una búsqueda que se vio correr, y se quita solo', () => {
    const { result, rerender } = renderHook(({ s }) => useFinishNotice(s), {
      initialProps: { s: running },
    });
    expect(result.current.notice).toBeNull();

    rerender({ s: finished });
    expect(result.current.notice?.text).toBe(
      `Búsqueda lista: ${String(finished.results_count)} notas`,
    );
    // Con la pestaña a la vista el título no cambia.
    expect(document.title).toBe('Monitor de Noticias');

    act(() => {
      vi.advanceTimersByTime(NOTICE_MS);
    });
    expect(result.current.notice).toBeNull();
  });

  it('reabrir una búsqueda ya terminada no avisa', () => {
    const { result } = renderHook(() => useFinishNotice(finished));

    expect(result.current.notice).toBeNull();
  });

  it('con la pestaña oculta cambia el título y lo regresa al volver', () => {
    const { rerender } = renderHook(({ s }) => useFinishNotice(s), {
      initialProps: { s: running },
    });
    setHidden(true);
    rerender({ s: finished });

    expect(document.title).toBe(`✓ Búsqueda lista: ${String(finished.results_count)} notas`);

    setHidden(false);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(document.title).toBe('Monitor de Noticias');
  });
});
