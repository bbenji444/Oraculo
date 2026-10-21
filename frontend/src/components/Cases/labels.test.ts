import { describe, expect, it } from 'vitest';

import {
  caseSummary,
  LEGAL_STATUS_OPTIONS,
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
