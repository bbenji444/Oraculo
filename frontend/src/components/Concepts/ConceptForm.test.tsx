// @vitest-environment jsdom
/** Formulario de conceptos en una pantalla (ADR-0109, ADR-0110). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
const SAVED = {
  ...FGR,
  id: 9,
  name: 'Robo de vehículos',
  description: 'robo de autos con violencia en Jalisco',
  keywords: ['roban autos', 'roban camionetas'],
  exclude_terms: ['seguro de auto'],
  query_mode: 'open',
  query_mode_label: 'como en Google',
};

/** Responde según la ruta: la propuesta de la IA o el concepto guardado. */
function stubApi() {
  // El servicio llama a fetch con la ruta como texto.
  const spy = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) => {
    const body = url.endsWith('/suggest') ? PROPOSAL : SAVED;
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
  vi.stubGlobal('fetch', spy);
  return spy;
}

function bodyOf(spy: ReturnType<typeof stubApi>, index: number): unknown {
  const [, init] = spy.mock.calls[index] as [string, RequestInit];
  return JSON.parse(init.body as string);
}

function renderForm(concept?: Concept) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onSaved = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ConceptForm concept={concept} embedded onSaved={onSaved} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
  return onSaved;
}

function writeIntent(text: string) {
  fireEvent.change(screen.getByLabelText('¿Qué noticias quieres seguir?'), {
    target: { value: text },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ConceptForm en una pantalla (ADR-0110)', () => {
  it('todo está a la vista: sin pasos ni selector de modo', () => {
    stubApi();
    renderForm();

    expect(screen.getByLabelText('Frases de búsqueda')).toBeTruthy();
    expect(screen.getByLabelText('Nombre')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Prefiero escribirlas yo' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Frases exactas' })).toBeNull();
  });

  it('la IA llena las frases ahí mismo para revisarlas', async () => {
    const spy = stubApi();
    renderForm();

    writeIntent('robo de autos con violencia en Jalisco');
    fireEvent.click(screen.getByRole('button', { name: 'Proponer frases con la IA' }));

    expect((await screen.findByRole('status')).textContent).toContain('La IA propuso 2 frases');
    expect(spy.mock.calls[0]?.[0]).toBe('/api/v1/concepts/suggest');
    expect(bodyOf(spy, 0)).toEqual({ description: 'robo de autos con violencia en Jalisco' });
    expect(screen.getByLabelText<HTMLInputElement>('Nombre').value).toBe('Robo de vehículos');
    expect(screen.getByText('roban camionetas')).toBeTruthy();
  });

  it('basta con escribir lo que se busca: la IA pone lo demás al guardar', async () => {
    const spy = stubApi();
    const onSaved = renderForm();

    writeIntent('robo de autos con violencia en Jalisco');
    fireEvent.click(screen.getByRole('button', { name: 'Crear concepto' }));

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalled();
    });
    expect(spy.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/concepts/suggest',
      '/api/v1/concepts',
    ]);
    expect(bodyOf(spy, 1)).toMatchObject({
      name: 'Robo de vehículos',
      description: 'robo de autos con violencia en Jalisco',
      keywords: ['roban autos', 'roban camionetas'],
      query_mode: 'open',
    });
  });

  it('sin nada escrito avisa qué falta y no llama a nadie', () => {
    const spy = stubApi();
    renderForm();

    fireEvent.click(screen.getByRole('button', { name: 'Crear concepto' }));

    expect(screen.getByText('Escribe qué noticias quieres seguir.')).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
  });

  it('uno exacto se edita sin cambiar de modo y lo explica', () => {
    stubApi();
    renderForm(FGR);

    expect(screen.getByText(/se busca con frases exactas/)).toBeTruthy();
    expect(screen.getByLabelText('Palabras clave')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Proponer frases con la IA' })).toBeNull();
  });
});
