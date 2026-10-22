import { describe, expect, it } from 'vitest';

import {
  caseSummary,
  confidencePercent,
  draftProblem,
  LEGAL_STATUS_OPTIONS,
  mergeAction,
  RELATIONSHIP_TYPE_OPTIONS,
  relationshipPhrase,
  SENSITIVITY_OPTIONS,
  SENSITIVITY_TONE,
  STATUS_TONE,
} from './labels';

describe('etiquetas de casos', () => {
  it('ofrece las tres sensibilidades en español, de menor a mayor reserva', () => {
    expect(SENSITIVITY_OPTIONS).toEqual([
      { value: 'normal', label: 'Normal' },
      { value: 'restricted', label: 'Reservado' },
      { value: 'confidential', label: 'Confidencial' },
    ]);
    expect(Object.keys(SENSITIVITY_TONE)).toEqual(['normal', 'restricted', 'confidential']);
    expect(Object.keys(STATUS_TONE)).toEqual(['open', 'closed', 'archived']);
  });

  it('resume cuántas notas tiene y cuándo cambió (hora de CDMX)', () => {
    expect(caseSummary({ article_count: 8, updated_at: '2026-10-21T16:40:42Z' })).toBe(
      '8 notas · actualizado 21 oct',
    );
    expect(caseSummary({ article_count: 1, updated_at: '2026-10-21T03:00:00Z' })).toBe(
      '1 nota · actualizado 20 oct',
    );
    expect(caseSummary({ article_count: 0, updated_at: '2026-10-21T16:40:42Z' })).toBe(
      'sin notas todavía · actualizado 21 oct',
    );
  });
});

describe('estatus legal al confirmar', () => {
  it('son los siete de la API y nunca "culpable" (ADR-0105)', () => {
    const values = LEGAL_STATUS_OPTIONS.map((o) => o.value);
    expect(values).toHaveLength(7);
    expect(values).not.toContain('culpable');
    expect(LEGAL_STATUS_OPTIONS.map((o) => o.label)).not.toContain('culpable');
  });
});

describe('vínculos (9.5)', () => {
  const draft = { entityA: 1, entityB: 2, type: 'family' as const, customLabel: '', notes: '' };

  it('ofrece los ocho tipos de la API y marca los que tienen sentido', () => {
    expect(RELATIONSHIP_TYPE_OPTIONS.map((o) => o.value).sort()).toEqual([
      'appears_with',
      'associate',
      'custom',
      'employer',
      'family',
      'located_in',
      'owns',
      'same_event',
    ]);
    expect(RELATIONSHIP_TYPE_OPTIONS.filter((o) => o.directed).map((o) => o.value)).toEqual([
      'owns',
      'employer',
      'located_in',
      'custom',
    ]);
  });

  it('dice qué le falta a un vínculo antes de mandarlo', () => {
    expect(draftProblem(draft)).toBeNull();
    expect(draftProblem({ ...draft, entityB: 0 })).toBe('Elige las dos entidades.');
    expect(draftProblem({ ...draft, entityB: 1 })).toBe('Elige dos entidades distintas.');
    expect(draftProblem({ ...draft, type: 'custom', customLabel: '   ' })).toBe(
      'Escribe la etiqueta del vínculo.',
    );
    expect(draftProblem({ ...draft, type: 'custom', customLabel: 'socio' })).toBeNull();
    expect(draftProblem({ ...draft, type: 'custom', customLabel: 'x'.repeat(81) })).toMatch(
      /hasta 80/,
    );
    expect(draftProblem({ ...draft, notes: 'x'.repeat(1001) })).toMatch(/hasta 1000/);
  });

  it('lee la confianza y el sentido de un vínculo', () => {
    expect(confidencePercent(0.7)).toBe('70 %');
    expect(
      relationshipPhrase({
        type: 'owns',
        type_label: 'es dueño de',
        custom_label: null,
        symmetric: false,
      }),
    ).toBe('→ es dueño de →');
    expect(
      relationshipPhrase({
        type: 'custom',
        type_label: 'otro (etiqueta propia)',
        custom_label: 'socio en el salón',
        symmetric: false,
      }),
    ).toBe('→ socio en el salón →');
  });
});

describe('«Es la misma que…» (9.5)', () => {
  it('deja la confirmada; si están igual, la elegida en la lista', () => {
    const suggested = { id: 4, review_status: 'suggested' as const };
    const confirmed = { id: 9, review_status: 'confirmed' as const };
    expect(mergeAction(suggested, confirmed)).toEqual({ kind: 'merge', keepId: 9, mergeId: 4 });
    expect(mergeAction(confirmed, suggested)).toEqual({ kind: 'merge', keepId: 9, mergeId: 4 });
    expect(mergeAction(suggested, { id: 7, review_status: 'suggested' })).toEqual({
      kind: 'merge',
      keepId: 7,
      mergeId: 4,
    });
  });
});
