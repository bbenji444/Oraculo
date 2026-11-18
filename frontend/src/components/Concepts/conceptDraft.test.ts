import { describe, expect, it } from 'vitest';

import type { ConceptInput, TermSuggestion } from '../../services/concepts';
import { MODE_COPY, MODE_OPTIONS, applySuggestion } from './conceptDraft';

const draft: ConceptInput = {
  name: '',
  description: 'robo de autos con violencia en Jalisco',
  keywords: ['robo'],
  exclude_terms: ['seguro'],
  color: '#2E86DE',
  is_active: true,
  query_mode: 'exact',
};
const proposal: TermSuggestion = {
  name: 'Robo de vehículos',
  keywords: ['roban autos', 'roban camionetas'],
  exclude_terms: [],
  query_mode: 'open',
  model: 'gpt-6-luna',
  cost_usd: 0.0001,
};

describe('applySuggestion', () => {
  it('pone las frases, las exclusiones y el modo de la IA', () => {
    const next = applySuggestion(draft, proposal);

    expect(next).toEqual({
      ...draft,
      name: 'Robo de vehículos',
      keywords: ['roban autos', 'roban camionetas'],
      exclude_terms: [],
      query_mode: 'open',
    });
  });

  it('no pisa el nombre que la persona ya escribió', () => {
    expect(applySuggestion({ ...draft, name: 'Robo Jalisco' }, proposal).name).toBe('Robo Jalisco');
  });
});

describe('textos de cada modo', () => {
  it('el recomendado va primero', () => {
    expect(MODE_OPTIONS.map((o) => o.value)).toEqual(['open', 'exact']);
  });

  it('en «como en Google» la descripción es lo que se juzga', () => {
    expect(MODE_COPY.open.descriptionLabel).toBe('Lo que buscas, en tus palabras');
    expect(MODE_COPY.open.keywordsLabel).toBe('Frases');
    expect(MODE_COPY.exact.keywordsLabel).toBe('Palabras clave');
  });
});
