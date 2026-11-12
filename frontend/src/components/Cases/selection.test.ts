import { describe, expect, it } from 'vitest';

import { entity } from '../../test/caseFixtures';
import {
  bulkDecisions,
  bulkNotice,
  countLabel,
  selectionState,
  selectionSummary,
  toggleKey,
  toggleKeys,
} from './selection';

describe('casilla de un grupo', () => {
  it('dice si el grupo está marcado completo, a medias o nada', () => {
    expect(selectionState(new Set([1, 2]), [1, 2])).toBe('all');
    expect(selectionState(new Set([1]), [1, 2])).toBe('some');
    expect(selectionState(new Set([9]), [1, 2])).toBe('none');
  });

  it('un grupo incompleto se completa y uno completo se vacía, sin tocar lo demás', () => {
    expect([...toggleKeys(new Set([1, 9]), [1, 2])].sort()).toEqual([1, 2, 9]);
    expect([...toggleKeys(new Set([1, 2, 9]), [1, 2])]).toEqual([9]);
  });

  it('marca y desmarca una sola llave sin cambiar la selección original', () => {
    const before = new Set(['a']);
    expect([...toggleKey(before, 'b', true)]).toEqual(['a', 'b']);
    expect([...toggleKey(before, 'a', false)]).toEqual([]);
    expect([...before]).toEqual(['a']);
  });
});

describe('qué se manda en bloque (D1)', () => {
  const juan = entity(1, 'person', 'Juan', { suggested: 'detained' });
  const ana = entity(2, 'person', 'Ana', { legal: 'victim', suggested: 'witness' });
  const dora = entity(3, 'person', 'Dora');
  const fgr = entity(4, 'org', 'FGR');

  it('al confirmar, cada persona lleva el estatus que se ve en su renglón', () => {
    const chosen = new Map([[1, 'charged' as const]]);

    expect(bulkDecisions([juan, ana, dora, fgr], 'confirm', chosen)).toEqual([
      // Lo que eligió el analista en el menú gana.
      { entity_id: 1, legal_status: 'charged' },
      // Sin tocar el menú: el confirmado antes que el sugerido.
      { entity_id: 2, legal_status: 'victim' },
      // La nota no dice nada: «mencionado».
      { entity_id: 3, legal_status: 'mentioned' },
      // Lo que no es persona no lleva estatus.
      { entity_id: 4, legal_status: null },
    ]);
  });

  it('al descartar nadie lleva estatus', () => {
    expect(bulkDecisions([juan, fgr], 'discard', new Map([[1, 'charged' as const]]))).toEqual([
      { entity_id: 1, legal_status: null },
      { entity_id: 4, legal_status: null },
    ]);
  });
});

describe('lo elegido en palabras', () => {
  it('cuenta por tipo con singular y plural', () => {
    const people = [
      entity(1, 'person', 'A', { typeLabel: 'persona' }),
      entity(2, 'person', 'B', { typeLabel: 'persona' }),
    ];
    const org = entity(3, 'org', 'C', { typeLabel: 'organización' });
    const place = entity(4, 'place', 'D', { typeLabel: 'lugar' });

    expect(selectionSummary([...people, org])).toBe('2 personas y 1 organización');
    expect(selectionSummary([...people, org, place])).toBe('2 personas, 1 organización y 1 lugar');
    expect(selectionSummary([org])).toBe('1 organización');
    expect(selectionSummary([])).toBe('');
  });

  it('avisa cuánto cambió y cuánto ya estaba así', () => {
    expect(bulkNotice('confirm', { changed: 5, unchanged: 2 })).toBe(
      'Listo: se confirmaron 5. 2 ya estaban así.',
    );
    expect(bulkNotice('confirm', { changed: 1, unchanged: 0 })).toBe('Listo: se confirmó 1.');
    expect(bulkNotice('discard', { changed: 3, unchanged: 1 })).toBe(
      'Listo: se descartaron 3. 1 ya estaba así.',
    );
    expect(bulkNotice('discard', { changed: 1, unchanged: 0 })).toBe('Listo: se descartó 1.');
  });

  it('«1 vínculo», «3 vínculos»', () => {
    expect(countLabel(1, 'vínculo', 'vínculos')).toBe('1 vínculo');
    expect(countLabel(3, 'vínculo', 'vínculos')).toBe('3 vínculos');
  });
});
