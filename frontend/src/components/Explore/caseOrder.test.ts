import { describe, expect, it } from 'vitest';

import type { Case } from '../../services/cases';
import { withLastFirst } from './caseOrder';

function item(id: string): Case {
  return {
    id,
    name: `Caso ${id}`,
    description: '',
    status: 'open',
    status_label: 'abierto',
    sensitivity: 'normal',
    sensitivity_label: 'normal',
    created_by: 'desarrollo',
    closed_at: null,
    created_at: '2026-10-21T10:00:00Z',
    updated_at: '2026-10-21T10:00:00Z',
    article_count: 0,
    role: 'owner',
    has_article: false,
  };
}

describe('orden de los casos en «Agregar al caso»', () => {
  const cases = [item('a'), item('b'), item('c')];

  it('pone primero el último caso usado y conserva el resto', () => {
    expect(withLastFirst(cases, 'c').map((c) => c.id)).toEqual(['c', 'a', 'b']);
  });

  it('sin último caso, o si ya no está abierto, deja el orden de la API', () => {
    expect(withLastFirst(cases, null).map((c) => c.id)).toEqual(['a', 'b', 'c']);
    expect(withLastFirst(cases, 'archivado').map((c) => c.id)).toEqual(['a', 'b', 'c']);
  });
});
