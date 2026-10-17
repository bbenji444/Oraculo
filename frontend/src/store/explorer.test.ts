import { beforeEach, describe, expect, it } from 'vitest';

import { searchInput, useExplorerStore } from './explorer';

const initial = useExplorerStore.getState();

beforeEach(() => {
  useExplorerStore.setState(initial, true);
});

describe('cuerpo de la búsqueda', () => {
  it('falta región o concepto: no hay búsqueda', () => {
    expect(searchInput({ regionId: null, conceptIds: [3], range: { kind: '7' } })).toBeNull();
    expect(searchInput({ regionId: 272, conceptIds: [], range: { kind: '7' } })).toBeNull();
  });

  it('rangos rápidos en días y conceptos ordenados', () => {
    expect(searchInput({ regionId: 272, conceptIds: [5, 3], range: { kind: '7' } })).toEqual({
      region_id: 272,
      concept_ids: [3, 5],
      days: 7,
    });
    expect(searchInput({ regionId: 272, conceptIds: [3], range: { kind: 'today' } })?.days).toBe(1);
    expect(searchInput({ regionId: 272, conceptIds: [3], range: { kind: '30' } })?.days).toBe(30);
  });

  it('personalizado necesita las dos fechas', () => {
    const custom = { kind: 'custom' as const, from: '2026-10-01', to: '2026-10-07' };

    expect(searchInput({ regionId: 272, conceptIds: [3], range: custom })).toEqual({
      region_id: 272,
      concept_ids: [3],
      date_from: '2026-10-01',
      date_to: '2026-10-07',
    });
    expect(
      searchInput({
        regionId: 272,
        conceptIds: [3],
        range: { kind: 'custom', from: '2026-10-01' },
      }),
    ).toBeNull();
  });
});

describe('store de Explorar', () => {
  it('elegir región o nota detiene el giro', () => {
    const store = useExplorerStore.getState();
    store.setSpinning(true);
    store.selectRegion(272);

    expect(useExplorerStore.getState()).toMatchObject({ regionId: 272, spinning: false });

    store.setSpinning(true);
    store.selectArticle(11);
    expect(useExplorerStore.getState()).toMatchObject({ articleId: 11, spinning: false });
  });

  it('los conceptos se prenden y apagan', () => {
    const store = useExplorerStore.getState();
    store.toggleConcept(3);
    store.toggleConcept(5);
    store.toggleConcept(3);

    expect(useExplorerStore.getState().conceptIds).toEqual([5]);
  });

  it('abrir otra búsqueda olvida la nota y el filtro', () => {
    const store = useExplorerStore.getState();
    store.selectArticle(11);
    store.setListFilter('false');
    store.openSearch('abc');

    expect(useExplorerStore.getState()).toMatchObject({
      searchId: 'abc',
      articleId: null,
      listFilter: 'all',
    });
  });

  it('"sin animación" también detiene el giro', () => {
    const store = useExplorerStore.getState();
    store.setSpinning(true);
    store.setMotion('off');

    expect(useExplorerStore.getState()).toMatchObject({ motion: 'off', spinning: false });
  });
});

describe('reabrir una búsqueda', () => {
  it('restaura región, conceptos y fechas, y detiene el giro', () => {
    const store = useExplorerStore.getState();
    store.setSpinning(true);
    store.selectArticle(11);
    store.restoreSearch({
      searchId: 'abc',
      regionId: 272,
      conceptIds: [3],
      dateFrom: '2026-10-10',
      dateTo: '2026-10-17',
    });

    expect(useExplorerStore.getState()).toMatchObject({
      searchId: 'abc',
      regionId: 272,
      conceptIds: [3],
      range: { kind: 'custom', from: '2026-10-10', to: '2026-10-17' },
      articleId: null,
      spinning: false,
    });
  });
});
