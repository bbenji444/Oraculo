/** Temas de la cronología (F12.7), con títulos reales de la corrida FGR del 26/10/2026. */
import { describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import { foldName, groupThemes, THEME_MIN_ITEMS } from './themes';
import { storyItems } from './timelineData';

let nextId = 1;

function note(title: string, hour: number, place: string | null = null): Article {
  const id = nextId++;
  return {
    article_id: id,
    title,
    source_name: null,
    source_domain: null,
    url: `https://medio.mx/${String(id)}`,
    published_at: new Date(Date.UTC(2026, 9, 26, hour)).toISOString(),
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts: [],
    primary_location: place
      ? {
          mention: place,
          role: 'event',
          precision: 'state',
          confidence: 1,
          is_primary: true,
          region_id: 1,
          region_code: '08',
          place,
          lon: null,
          lat: null,
        }
      : null,
    in_region: null,
    providers: [],
    story_id: null,
  };
}

const JAUREGUI = [
  'Vinculan a Jáuregui por traición a la patria',
  'Caravana por Jáuregui llegó a FGR Chihuahua',
  'Exigen en FGR libertad de Jáuregui',
  'Protestan por jáuregui frente a la FGR',
  'Defensa de César Jáuregui compara su proceso con juicio de Maximiliano',
  'Declaraciones de Jáuregui ante los medios lo hundieron',
];

describe('temas de la cronología', () => {
  it('junta en un bloque los hechos que nombran a la misma persona', () => {
    const articles = [
      ...JAUREGUI.map((title, i) => note(title, 10 - i, 'Chihuahua')),
      note('AGRADECE CESAR JAUREGUI MUESTRAS DE APOYO', 2),
      note('La FGR detiene a Carlos Iván El Chore, operador de Los Gigios', 11),
    ];

    const rows = groupThemes(storyItems(articles));

    expect(rows).toHaveLength(2);
    expect(rows[0]?.kind).toBe('item');
    const theme = rows[1];
    expect(theme?.kind).toBe('theme');
    if (theme?.kind !== 'theme') return;
    expect(theme.label).toBe('Jáuregui');
    // El título en mayúsculas también entra, aunque no sirva para descubrir el tema.
    expect(theme.items).toHaveLength(JAUREGUI.length + 1);
    expect(theme.notes).toBe(JAUREGUI.length + 1);
  });

  it('el bloque ocupa el lugar de su hecho más reciente', () => {
    const articles = [
      note('La FGR detiene a Carlos Iván El Chore', 12),
      ...JAUREGUI.map((title, i) => note(title, 11 - i)),
      note('Asegura FGR más de 600 prendas apócrifas en Nuevo León', 1),
    ];

    const rows = groupThemes(storyItems(articles));

    expect(rows.map((row) => row.kind)).toEqual(['item', 'theme', 'item']);
  });

  it(`menos de ${String(THEME_MIN_ITEMS)} hechos no son tema`, () => {
    const articles = JAUREGUI.slice(0, THEME_MIN_ITEMS - 1).map((title, i) => note(title, i));

    expect(groupThemes(storyItems(articles)).every((row) => row.kind === 'item')).toBe(true);
  });

  it('los lugares no son tema: para eso está el filtro por estado', () => {
    const articles = [
      'Balacera en Culiacán deja dos muertos',
      'Cierran escuelas en Culiacán por violencia',
      'Hallan restos en fosa de Culiacán',
      'Marchan en Culiacán por desaparecidos',
      'Detienen a tres en Culiacán con armas',
      'Liberan carretera a Culiacán tras bloqueo',
    ].map((title, i) => note(title, i, 'Culiacán'));

    expect(groupThemes(storyItems(articles)).every((row) => row.kind === 'item')).toBe(true);
  });

  it('compara sin acentos y conserva la Ñ', () => {
    expect(foldName('Jáuregui')).toBe('JAUREGUI');
    expect(foldName('Peñón')).toBe('PEÑON');
  });
});
