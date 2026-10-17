import { describe, expect, it } from 'vitest';

import type { RegionDetail } from '../../services/regions';
import { chainOf } from './regionChain';

function detail(id: number, level: RegionDetail['level'], ancestors: RegionDetail['ancestors']) {
  return { id, level, ancestors } as unknown as RegionDetail;
}

const MEXICO = { id: 1, level: 'country' as const, code: 'MEX', name: 'México' };
const JALISCO = { id: 14, level: 'state' as const, code: '14', name: 'Jalisco' };
const GUADALAJARA = {
  id: 1084,
  level: 'municipality' as const,
  code: '14039',
  name: 'Guadalajara',
};

describe('cadena de filtros', () => {
  it('sin región no hay nada elegido', () => {
    expect(chainOf(undefined)).toEqual({ stateId: null, municipalityId: null, localityId: null });
  });

  it('un estado, un municipio y una localidad', () => {
    expect(chainOf(detail(14, 'state', [MEXICO]))).toEqual({
      stateId: 14,
      municipalityId: null,
      localityId: null,
    });
    expect(chainOf(detail(1084, 'municipality', [MEXICO, JALISCO])).municipalityId).toBe(1084);
    expect(chainOf(detail(9, 'locality', [MEXICO, JALISCO, GUADALAJARA]))).toEqual({
      stateId: 14,
      municipalityId: 1084,
      localityId: 9,
    });
  });
});
