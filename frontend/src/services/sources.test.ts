import { describe, expect, it } from 'vitest';

import { chosenSources, type SourceOption } from './sources';

const OPTIONS: SourceOption[] = [
  {
    id: 'google_news_rss',
    label: 'Google News RSS',
    paid: false,
    configured: true,
    default_on: true,
  },
  { id: 'indice_local', label: 'Índice local', paid: false, configured: true, default_on: true },
  { id: 'searchapi', label: 'SearchApi', paid: true, configured: false, default_on: true },
];

describe('fuentes con las que se busca', () => {
  it('sin elegir: las de por defecto que estén configuradas', () => {
    expect(chosenSources(OPTIONS, null)).toEqual(['google_news_rss', 'indice_local']);
  });

  it('lo elegido manda, en el orden de pantalla y sin las no configuradas', () => {
    expect(chosenSources(OPTIONS, ['searchapi', 'indice_local'])).toEqual(['indice_local']);
  });

  it('con todo apagado no queda ninguna', () => {
    expect(chosenSources(OPTIONS, [])).toEqual([]);
  });
});
