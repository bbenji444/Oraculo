// @vitest-environment jsdom
/** Editor de una subdivisión y las palabras de su tema general (02/11/2026). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Category } from '../../services/categories';
import type { Concept } from '../../services/concepts';
import { SubdivisionForm } from './SubdivisionForm';

const HOMICIDIO: Category = {
  id: 5,
  name: 'Homicidio',
  description: 'Asesinatos',
  is_other: false,
  color: '#FF4D6D',
  symbol: null,
  is_active: true,
  topic_concept_id: 21,
};
const OTROS: Category = { ...HOMICIDIO, id: 14, name: 'Otros', is_other: true };
const TOPIC: Concept = {
  id: 21,
  name: 'Homicidio',
  description: '',
  keywords: ['homicidio', 'asesinato'],
  exclude_terms: ['película'],
  color: '#FF4D6D',
  is_active: true,
  category_id: 5,
  created_by: 'semilla',
  created_at: '2026-11-02T18:00:00Z',
  updated_at: '2026-11-02T18:00:00Z',
};

function stubApi() {
  const spy = vi.fn<typeof fetch>((input) =>
    Promise.resolve(
      // requestJson pide con la ruta en texto.
      new Response(
        JSON.stringify(
          typeof input === 'string' && input.includes('categories') ? HOMICIDIO : TOPIC,
        ),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    ),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

function renderForm(category: Category, topic: Concept | undefined) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SubdivisionForm category={category} topic={topic} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('SubdivisionForm', () => {
  it('manda a cada ruta solo lo que cambió', async () => {
    const spy = stubApi();
    renderForm(HOMICIDIO, TOPIC);

    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Homicidio doloso' } });
    fireEvent.change(screen.getByLabelText('Palabras clave'), {
      target: { value: 'feminicidio,' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await screen.findByRole('status');
    const calls = spy.mock.calls.map(([url, init]) => [
      url,
      init?.method,
      JSON.parse(init?.body as string) as unknown,
    ]);
    expect(calls).toEqual([
      ['/api/v1/categories/5', 'PATCH', { name: 'Homicidio doloso' }],
      [
        '/api/v1/concepts/21',
        'PATCH',
        { keywords: ['homicidio', 'asesinato', 'feminicidio'], exclude_terms: ['película'] },
      ],
    ]);
  });

  it('sin cambios no manda nada', async () => {
    const spy = stubApi();
    renderForm(HOMICIDIO, TOPIC);

    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

    await screen.findByRole('status');
    expect(spy).not.toHaveBeenCalled();
  });

  it('«Otros» no se apaga y no tiene palabras de tema', async () => {
    stubApi();
    renderForm(OTROS, undefined);

    const toggle = screen.getByRole('switch', { name: 'Prendida' });
    expect((toggle as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByLabelText('Palabras clave')).toBeNull();
    await waitFor(() => {
      expect(screen.getByText(/«Otros» no se apaga/)).toBeTruthy();
    });
  });
});

describe('SubdivisionForm: agregar y borrar (09/11/2026)', () => {
  it('agrega una subdivisión con las palabras de su tema general', async () => {
    const spy = stubApi();
    const onCreated = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SubdivisionForm topic={undefined} onClose={vi.fn()} onCreated={onCreated} />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Feminicidio' } });
    fireEvent.change(screen.getByLabelText('Palabras clave'), {
      target: { value: 'feminicidio,' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar subdivisión' }));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalled();
    });
    const [url, init] = spy.mock.calls[0] ?? [];
    expect([url, init?.method]).toEqual(['/api/v1/categories', 'POST']);
    expect(JSON.parse(init?.body as string)).toEqual({
      name: 'Feminicidio',
      description: '',
      color: '#00D2FF',
      is_active: true,
      keywords: ['feminicidio'],
      exclude_terms: [],
    });
  });

  it('borrar pide confirmación y avisa que sus notas pasan a «Otros»', async () => {
    const spy = vi.fn<typeof fetch>(() =>
      Promise.resolve(
        new Response(JSON.stringify({ notes_moved_to_other: 3 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
    vi.stubGlobal('fetch', spy);
    const onClose = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SubdivisionForm category={HOMICIDIO} topic={TOPIC} onClose={onClose} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Borrar' }));
    expect(screen.getByRole('alertdialog').textContent).toContain('pasan a «Otros»');
    expect(spy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Sí, borrar' }));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(spy.mock.calls[0]?.[0]).toBe('/api/v1/categories/5');
    expect(spy.mock.calls[0]?.[1]?.method).toBe('DELETE');
  });

  it('«Otros» no se puede borrar', () => {
    stubApi();
    renderForm(OTROS, undefined);

    expect(screen.queryByRole('button', { name: 'Borrar' })).toBeNull();
  });
});
