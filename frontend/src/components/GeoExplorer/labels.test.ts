import { describe, expect, it } from 'vitest';

import { LEVEL_LABEL } from './labels';

describe('labels', () => {
  it('niveles en español', () => {
    expect(Object.values(LEVEL_LABEL)).toEqual(['País', 'Estado', 'Municipio', 'Localidad']);
  });
});
