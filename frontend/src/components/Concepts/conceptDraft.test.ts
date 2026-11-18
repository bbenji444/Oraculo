import { describe, expect, it } from 'vitest';

import type { ConceptInput, TermSuggestion } from '../../services/concepts';
import { MODE_COPY, applySuggestion, fillMissing, needsProposal } from './conceptDraft';

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
  exclude_terms: ['seguro de auto'],
  query_mode: 'open',
  model: 'gpt-6-luna',
  cost_usd: 0.0001,
};
const open: ConceptInput = { ...draft, query_mode: 'open', keywords: [], exclude_terms: [] };

describe('applySuggestion', () => {
  it('pone las frases, las exclusiones y el modo de la IA', () => {
    const next = applySuggestion(draft, proposal);

    expect(next).toEqual({
      ...draft,
      name: 'Robo de vehículos',
      keywords: ['roban autos', 'roban camionetas'],
      exclude_terms: ['seguro de auto'],
      query_mode: 'open',
    });
  });

  it('no pisa el nombre que la persona ya escribió', () => {
    expect(applySuggestion({ ...draft, name: 'Robo Jalisco' }, proposal).name).toBe('Robo Jalisco');
  });
});

describe('al guardar con solo lo que se busca (ADR-0110)', () => {
  it('pide a la IA lo que falta en un concepto «como en Google»', () => {
    expect(needsProposal(open)).toBe(true);
    expect(needsProposal({ ...open, name: 'Robo', keywords: ['roban autos'] })).toBe(false);
    // Sin descripción no hay qué proponer; un exacto no se toca.
    expect(needsProposal({ ...open, description: '  ' })).toBe(false);
    expect(needsProposal({ ...draft, name: '' })).toBe(false);
  });

  it('llena solo lo que falta', () => {
    expect(fillMissing(open, proposal)).toEqual({
      ...open,
      name: 'Robo de vehículos',
      keywords: ['roban autos', 'roban camionetas'],
      exclude_terms: ['seguro de auto'],
    });
    const written = { ...open, keywords: ['roban autos'] };
    // Con frases escritas a mano solo pone el nombre.
    expect(fillMissing(written, proposal)).toEqual({ ...written, name: 'Robo de vehículos' });
  });
});

describe('textos de cada modo', () => {
  it('en «como en Google» la descripción es lo que se juzga', () => {
    expect(MODE_COPY.open.descriptionLabel).toBe('¿Qué noticias quieres seguir?');
    expect(MODE_COPY.open.explanation).toBeNull();
    expect(MODE_COPY.exact.keywordsLabel).toBe('Palabras clave');
  });
});
