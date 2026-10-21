import { describe, expect, it } from 'vitest';

import { caseSummary, SENSITIVITY_OPTIONS, SENSITIVITY_TONE, STATUS_TONE } from './labels';

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
