// @vitest-environment jsdom
/** Formulario de conceptos en dos pasos: lo que se busca y luego las frases (ADR-0109). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Concept } from '../../services/concepts';
import { ConceptForm } from './ConceptForm';

const PROPOSAL = {
  name: 'Robo de vehículos',
  keywords: ['roban autos', 'roban camionetas'],
  exclude_terms: ['seguro de auto'],
  query_mode: 'open',
  model: 'gpt-6-luna',
  cost_usd: 0.0001,
};
const FGR: Concept = {
  id: 1,
  name: 'FGR',
  description: '',
  keywords: ['FGR'],
  exclude_terms: [],
  color: '#2E86DE',
  is_active: true,
  category_id: null,
  query_mode: 'exact',
  query_mode_label: 'frases exactas',
  created_by: 'semilla',
  created_at: '2026-11-17T18:00:00Z',
  updated_at: '2026-11-17T18:00:00Z',
};

function stubApi(body: unknown = PROPOSAL) {
  const spy = vi.fn<typeof fetch>(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

function renderForm(concept?: Concept) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ConceptForm concept={concept} embedded onSaved={vi.fn()} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ConceptForm en dos pasos (ADR-0109)', () => {
  it('uno nuevo pregunta qué seguir y la IA llena las frases', async () => {
    const spy = stubApi();
    renderForm();

    fireEvent.change(screen.getByLabelText('¿Qué noticias quieres seguir?'), {
      target: { value: 'robo de autos con violencia en Jalisco' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Proponer frases' }));

    expect((await screen.findByRole('status')).textContent).toContain('La IA propuso 2 frases');
    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect([url, JSON.parse(init.body as string)]).toEqual([
      '/api/v1/concepts/suggest',
      { description: 'robo de autos con violencia en Jalisco' },
    ]);
    expect(screen.getByLabelText<HTMLInputElement>('Nombre').value).toBe('Robo de vehículos');
    expect(screen.getByText('roban camionetas')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Como en Google' }).getAttribute('aria-pressed'),
    ).toBe('true');
    // Lo que se escribió queda como lo que se juzga.
    const judged = screen.getByLabelText<HTMLTextAreaElement>(/Lo que buscas, en tus palabras/);
    expect(judged.value).toBe('robo de autos con violencia en Jalisco');
  });

  it('se puede saltar la IA y escribir las frases a mano', () => {
    const spy = stubApi();
    renderForm();

    fireEvent.click(screen.getByRole('button', { name: 'Prefiero escribirlas yo' }));

    expect(screen.getByLabelText('Frases')).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
  });

  it('uno guardado abre con todo y conserva su modo', () => {
    stubApi();
    renderForm(FGR);

    expect(screen.queryByLabelText('¿Qué noticias quieres seguir?')).toBeNull();
    expect(
      screen.getByRole('button', { name: 'Frases exactas' }).getAttribute('aria-pressed'),
    ).toBe('true');
    expect(screen.getByLabelText('Palabras clave')).toBeTruthy();
  });
});
