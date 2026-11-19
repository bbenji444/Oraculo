// @vitest-environment jsdom
/** «Cancelar búsqueda» mientras el barrido corre (ADR-0118). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Search } from '../../services/searches';
import { useMandoStore } from '../../store/mando';
import { CancelSearchButton } from './CancelSearchButton';

const RUNNING = {
  search_id: 'b01afb0d',
  status: 'running',
  trigger: 'manual',
} as Search;

function stubApi(status = 204, body: unknown = null) {
  const spy = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(
      new Response(body === null ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

function renderButton(search: Search) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CancelSearchButton search={search} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useMandoStore.setState({ editing: false });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('CancelSearchButton', () => {
  it('detiene la búsqueda y vuelve a la consulta para editarla', async () => {
    // Benji, 19/11/2026: «por si me equivoqué en algo o necesito regresar y editar».
    const spy = stubApi();
    renderButton(RUNNING);

    fireEvent.click(screen.getByRole('button', { name: /Cancelar búsqueda/ }));

    await waitFor(() => {
      expect(useMandoStore.getState().editing).toBe(true);
    });
    const [url, init] = spy.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/searches/b01afb0d/cancel');
    expect(init?.method).toBe('POST');
  });

  it('vuelve a la consola aunque el sondeo la vea cancelada antes que la respuesta', async () => {
    // Revisión del 19/11/2026: la consola quita el botón en cuanto ve «cancelled».
    stubApi();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <QueryClientProvider client={client}>
        <CancelSearchButton search={RUNNING} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: /Cancelar búsqueda/ }));
    unmount();

    await waitFor(() => {
      expect(useMandoStore.getState().editing).toBe(true);
    });
  });

  it('si ya terminó lo dice y no cambia la consola', async () => {
    stubApi(409, {
      error: {
        code: 'search_already_finished',
        message: 'La búsqueda ya terminó: no hay nada que cancelar.',
      },
    });
    renderButton(RUNNING);

    fireEvent.click(screen.getByRole('button', { name: /Cancelar búsqueda/ }));

    expect((await screen.findByRole('alert')).textContent).toContain('ya terminó');
    expect(useMandoStore.getState().editing).toBe(false);
  });

  it('no se ofrece en las corridas automáticas', () => {
    stubApi();
    renderButton({ ...RUNNING, trigger: 'automatic' });

    expect(screen.queryByRole('button', { name: /Cancelar búsqueda/ })).toBeNull();
  });
});
