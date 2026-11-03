import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  type Concept,
  type ConceptInput,
  createConcept,
  deleteConcept,
  fieldErrors,
  listConcepts,
  previewQueries,
  updateConcept,
} from './concepts';
import { ApiError } from './http';

const secuestro: Concept = {
  id: 2,
  name: 'Secuestro',
  description: '',
  keywords: ['secuestro', 'plagio'],
  exclude_terms: ['simulacro'],
  color: '#E74C3C',
  is_active: true,
  category_id: null,
  created_by: 'semilla',
  created_at: '2026-10-16T18:00:00Z',
  updated_at: '2026-10-16T18:00:00Z',
};
const draft: ConceptInput = {
  name: 'Extorsión telefónica',
  description: '',
  keywords: ['montadeudas'],
  exclude_terms: [],
  color: '#D35400',
  is_active: true,
};

function respondSequence(...bodies: { body: unknown; status?: number }[]) {
  const spy = vi.fn();
  for (const { body, status = 200 } of bodies) {
    spy.mockResolvedValueOnce(
      status === 204
        ? new Response(null, { status })
        : new Response(JSON.stringify(body), {
            status,
            headers: { 'Content-Type': 'application/json' },
          }),
    );
  }
  vi.stubGlobal('fetch', spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('listConcepts', () => {
  it('sigue el cursor hasta traer todas las páginas', async () => {
    const spy = respondSequence(
      { body: { items: [secuestro], next_cursor: 'abc' } },
      { body: { items: [{ ...secuestro, id: 3, name: 'Robo' }], next_cursor: null } },
    );

    const concepts = await listConcepts();

    expect(concepts.map((c) => c.id)).toEqual([2, 3]);
    expect(spy.mock.calls[1]?.[0]).toBe('/api/v1/concepts?limit=200&cursor=abc');
  });

  it('rechaza una respuesta con otra forma', async () => {
    respondSequence({ body: { items: [{ id: 'x' }], next_cursor: null } });

    await expect(listConcepts()).rejects.toMatchObject({ code: 'bad_format' });
  });
});

describe('crear, editar y borrar', () => {
  it('usa POST, PATCH y DELETE en las rutas correctas', async () => {
    const spy = respondSequence(
      { body: secuestro, status: 201 },
      { body: { ...secuestro, is_active: false } },
      { body: null, status: 204 },
    );

    await createConcept(draft);
    const updated = await updateConcept(2, { is_active: false });
    await deleteConcept(2);

    expect(updated.is_active).toBe(false);
    const calls = spy.mock.calls as [string, RequestInit][];
    expect(calls.map(([url, init]) => [url, init.method])).toEqual([
      ['/api/v1/concepts', 'POST'],
      ['/api/v1/concepts/2', 'PATCH'],
      ['/api/v1/concepts/2', 'DELETE'],
    ]);
  });
});

describe('previewQueries', () => {
  const preview = {
    concept_name: 'x',
    region: {},
    window: {},
    queries: [],
    total_queries: 0,
    total_credits: 0,
  };

  it('prueba un borrador enviando el formulario', async () => {
    const spy = respondSequence({ body: preview });

    await previewQueries({ regionId: 14, days: 30, draft });

    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/concepts/preview?region_id=14&days=30');
    expect(JSON.parse(init.body as string)).toEqual(draft);
  });

  it('prueba un concepto guardado sin cuerpo', async () => {
    const spy = respondSequence({ body: preview });

    await previewQueries({ regionId: 3, days: 7, conceptId: 2 });

    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/concepts/2/preview?region_id=3&days=7');
    expect(init.body).toBeUndefined();
  });
});

describe('fieldErrors', () => {
  it('agrupa los problemas de validación por campo', () => {
    const error = new ApiError('Datos inválidos.', 'invalid_concept', {
      problemas: [
        { campo: 'keywords', mensaje: '"hackéo" está repetida.' },
        { campo: 'keywords', mensaje: 'Sin comillas.' },
        { campo: 'color', mensaje: 'Formato #RRGGBB.' },
      ],
    });

    expect(fieldErrors(error)).toEqual({
      keywords: ['"hackéo" está repetida.', 'Sin comillas.'],
      color: ['Formato #RRGGBB.'],
    });
  });

  it('otros errores no tienen campos', () => {
    expect(fieldErrors(new ApiError('Ya existe.', 'concept_name_taken'))).toEqual({});
    expect(fieldErrors(new Error('x'))).toEqual({});
  });
});
