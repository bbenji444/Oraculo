// @vitest-environment jsdom
/** «+ Nuevo concepto» en Explorar y en «¿Qué rastrear?» (ADR-0109). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { NewConceptButton } from './NewConceptButton';

function stubMe() {
  const me = {
    username: 'benji',
    display_name: 'Benji',
    role: 'superuser',
    sections: [],
    auth_mode: 'dev',
  };
  const spy = vi.fn<typeof fetch>(() =>
    Promise.resolve(
      new Response(JSON.stringify(me), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

function renderButton() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewConceptButton className="hud-btn" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('NewConceptButton', () => {
  it('abre el formulario de dos pasos en una ventana', async () => {
    stubMe();
    renderButton();

    fireEvent.click(await screen.findByRole('button', { name: '+ Nuevo concepto' }));

    expect(screen.getByRole('dialog', { name: 'Nuevo concepto' })).toBeTruthy();
    expect(screen.getByLabelText('¿Qué noticias quieres seguir?')).toBeTruthy();
  });

  it('Esc cierra solo esta ventana, no la de abajo', async () => {
    stubMe();
    const below = vi.fn();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') below();
    };
    window.addEventListener('keydown', onKey);
    renderButton();
    fireEvent.click(await screen.findByRole('button', { name: '+ Nuevo concepto' }));

    fireEvent.keyDown(document.body, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(below).not.toHaveBeenCalled();
    window.removeEventListener('keydown', onKey);
  });
});
